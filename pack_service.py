#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sprite pack service.

Talks to the community sprite-pack repository on GitHub
(prep-stack/livesprite_gifs).  Layout of that repo:

  packs/<pack_id>/pack.json     - name, creator, version, preview, description
  packs/<pack_id>/preview.gif   - animated preview for the Browse window
  packs/<pack_id>/*.gif|*.png   - the sprite files themselves

Efficiency: one call to GitHub's *tree API* returns every file path with
a content sha.  pack.json files and previews are cached locally in
config/pack_cache/ and only re-downloaded when their sha changed, so
browsing costs 1 API request plus downloads for changed files only.
Actual pack downloads go through raw.githubusercontent.com which is not
rate-limited like the API.

Installed packs get a `.pack.json` marker in their assets/<id>/ folder
(pack id + version).  Folders without a marker were made by the user and
are never touched.  Updates overwrite/add GIF and PNG files but never
the user's settings.json.
"""

import json
import logging
import os
import shutil
import threading
from urllib.parse import quote

import requests
from PyQt5.QtCore import QObject, pyqtSignal

from config import ASSETS_DIR, CONFIG_DIR, load_json, save_json

logger = logging.getLogger(__name__)

PACKS_REPO = "prep-stack/livesprite_gifs"
PACKS_BRANCH = "main"
TREE_URL = (f"https://api.github.com/repos/{PACKS_REPO}"
            f"/git/trees/{PACKS_BRANCH}?recursive=1")
RAW_BASE = f"https://raw.githubusercontent.com/{PACKS_REPO}/{PACKS_BRANCH}/"

CACHE_DIR = os.path.join(CONFIG_DIR, "pack_cache")
CACHE_INDEX = os.path.join(CACHE_DIR, "index.json")  # repo path -> sha

MARKER_FILE = ".pack.json"   # written into installed asset folders


def parse_version(text):
    """'1.2.0' -> (1, 2, 0); unparsable parts become 0."""
    parts = []
    for chunk in str(text or "").strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def installed_pack_version(pack_id):
    """Version string from the marker in assets/<id>/, or None."""
    marker = load_json(os.path.join(ASSETS_DIR, pack_id, MARKER_FILE))
    if isinstance(marker, dict):
        return str(marker.get("version") or "0")
    return None


class PackService(QObject):
    """Fetches, installs and updates sprite packs in background threads."""

    # (ok, packs, error_message) - packs is a list of dicts
    packs_loaded = pyqtSignal(bool, list, str)
    # (pack_id, ok, message)
    install_finished = pyqtSignal(str, bool, str)
    # (updatable_pack_ids) - emitted after a quiet update check
    updates_checked = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "LiveSprite"

    # -- public API (all non-blocking) --------------------------------------
    def load_packs_async(self):
        threading.Thread(target=self._load_packs_safe, daemon=True).start()

    def install_async(self, pack):
        threading.Thread(
            target=self._install_safe, args=(pack,), daemon=True
        ).start()

    def check_updates_async(self):
        threading.Thread(target=self._check_updates_safe, daemon=True).start()

    # -- fetching ------------------------------------------------------------
    def _load_packs_safe(self):
        try:
            packs = self._fetch_packs()
            self.packs_loaded.emit(True, packs, "")
        except (requests.RequestException, ValueError, OSError) as e:
            logger.warning("Could not load sprite packs: %s", e)
            self.packs_loaded.emit(False, [], str(e))

    def _fetch_packs(self):
        """One tree API call -> list of pack dicts (cached pack.json/preview)."""
        resp = self._session.get(TREE_URL, timeout=15)
        if resp.status_code == 403:
            raise requests.RequestException(
                "GitHub rate limit reached - try again in a few minutes"
            )
        resp.raise_for_status()
        tree = resp.json().get("tree", [])

        by_pack = {}   # pack_id -> {repo_path: sha}
        for entry in tree:
            path = entry.get("path", "")
            if entry.get("type") != "blob" or not path.startswith("packs/"):
                continue
            parts = path.split("/")
            if len(parts) < 3:
                continue
            by_pack.setdefault(parts[1], {})[path] = entry.get("sha", "")

        os.makedirs(CACHE_DIR, exist_ok=True)
        index = load_json(CACHE_INDEX, default={}) or {}
        packs = []
        for pack_id, files in sorted(by_pack.items()):
            manifest_path = f"packs/{pack_id}/pack.json"
            if manifest_path not in files:
                logger.warning("Pack %s has no pack.json - skipped", pack_id)
                continue
            manifest = self._cached_json(manifest_path,
                                         files[manifest_path], index)
            if not isinstance(manifest, dict):
                continue
            preview_name = manifest.get("preview") or "preview.gif"
            preview_path = f"packs/{pack_id}/{preview_name}"
            preview_local = None
            if preview_path in files:
                preview_local = self._cached_file(
                    preview_path, files[preview_path], index
                )
            # Files to install: every gif/png except the preview
            payload = [
                (path, sha) for path, sha in sorted(files.items())
                if path.lower().endswith((".gif", ".png"))
                and path != preview_path
            ]
            packs.append({
                "id": pack_id,
                "name": str(manifest.get("name") or pack_id),
                "creator": str(manifest.get("creator") or "unknown"),
                "version": str(manifest.get("version") or "0"),
                "description": str(manifest.get("description") or ""),
                "preview_local": preview_local,
                "files": payload,
            })
        save_json(CACHE_INDEX, index)
        return packs

    def _cached_file(self, repo_path, sha, index):
        """Return a local path for repo_path, downloading only when changed."""
        local = os.path.join(CACHE_DIR, repo_path.replace("/", "_"))
        if index.get(repo_path) == sha and os.path.exists(local):
            return local
        data = self._download_raw(repo_path)
        with open(local, "wb") as f:
            f.write(data)
        index[repo_path] = sha
        return local

    def _cached_json(self, repo_path, sha, index):
        local = self._cached_file(repo_path, sha, index)
        try:
            with open(local, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Bad pack manifest %s: %s", repo_path, e)
            return None

    def _download_raw(self, repo_path):
        url = RAW_BASE + quote(repo_path)
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content

    # -- installing -----------------------------------------------------------
    def _install_safe(self, pack):
        try:
            self._install(pack)
            self.install_finished.emit(
                pack["id"], True,
                f"{pack['name']} v{pack['version']} installed"
            )
        except (requests.RequestException, OSError, ValueError) as e:
            logger.error("Pack install failed (%s): %s", pack.get("id"), e)
            self.install_finished.emit(pack["id"], False, str(e))

    def _install(self, pack):
        """Download the pack into assets/<id>/ (update-safe).

        GIF/PNG files are written/overwritten.  The user's settings.json
        is never touched.  Downloads go to a temp folder first so a
        half-failed download never leaves a broken pack behind.
        """
        dest = os.path.join(ASSETS_DIR, pack["id"])
        tmp = dest + ".part"
        if os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
        try:
            for repo_path, _sha in pack["files"]:
                filename = repo_path.split("/")[-1]
                data = self._download_raw(repo_path)
                with open(os.path.join(tmp, filename), "wb") as f:
                    f.write(data)
            # All downloads succeeded - move into place
            os.makedirs(dest, exist_ok=True)
            for name in os.listdir(tmp):
                target = os.path.join(dest, name)
                if os.path.exists(target):
                    os.remove(target)
                shutil.move(os.path.join(tmp, name), target)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        save_json(os.path.join(dest, MARKER_FILE), {
            "pack_id": pack["id"],
            "version": pack["version"],
        })
        logger.info("Installed pack %s v%s (%d files)",
                    pack["id"], pack["version"], len(pack["files"]))

    # -- update check -----------------------------------------------------------
    def _check_updates_safe(self):
        try:
            packs = self._fetch_packs()
        except (requests.RequestException, ValueError, OSError) as e:
            logger.info("Pack update check skipped: %s", e)
            return
        updatable = []
        for pack in packs:
            installed = installed_pack_version(pack["id"])
            if installed is None:
                continue  # not installed from the repo
            if parse_version(pack["version"]) > parse_version(installed):
                updatable.append(pack["id"])
        self.updates_checked.emit(updatable)
        if updatable:
            logger.info("Pack updates available: %s", ", ".join(updatable))
