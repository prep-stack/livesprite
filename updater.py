#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Update checker and installer.

Checks the newest release of the public GitHub repository and, when a
newer version exists, downloads its zip and installs it in place:

  * the check runs in a background thread (UI never blocks)
  * personal data is never touched: config/ and any asset folders the
    user added stay exactly as they are - the update only replaces
    program files
  * when running as a frozen exe the running executable cannot be
    overwritten, so a small helper .bat finishes the swap and restarts
    the program
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile

import requests
from PyQt5.QtCore import QObject, pyqtSignal

from config import BASE_DIR
from version import VERSION

logger = logging.getLogger(__name__)

GITHUB_REPO = "prep-stack/livesprite"
API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def parse_version(text):
    """'v2.1.0' or '2.1.0' -> (2, 1, 0); unparsable parts become 0."""
    text = (text or "").strip().lstrip("vV")
    parts = []
    for chunk in text.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


class Updater(QObject):
    """Checks GitHub releases and installs updates."""

    # (available, latest_version, zip_url) - emitted on the UI thread
    check_finished = pyqtSignal(bool, str, str)
    # (success, message)
    update_finished = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.latest_version = ""
        self.zip_url = ""

    # -- checking ---------------------------------------------------------
    def check_async(self):
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        try:
            resp = requests.get(
                API_LATEST, timeout=10,
                headers={"Accept": "application/vnd.github+json"},
            )
            if resp.status_code == 404:
                # No release published yet
                self.check_finished.emit(False, VERSION, "")
                return
            resp.raise_for_status()
            data = resp.json()
            tag = data.get("tag_name", "")
            zip_url = ""
            for asset in data.get("assets", []):
                if asset.get("name", "").lower().endswith(".zip"):
                    zip_url = asset.get("browser_download_url", "")
                    break
            newer = parse_version(tag) > parse_version(VERSION)
            self.latest_version = tag.lstrip("vV")
            self.zip_url = zip_url
            self.check_finished.emit(newer and bool(zip_url),
                                     self.latest_version, zip_url)
            logger.info("Update check: local %s, latest %s, newer=%s",
                        VERSION, tag, newer)
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.warning("Update check failed: %s", e)
            self.check_finished.emit(False, VERSION, "")

    # -- installing ---------------------------------------------------------
    def install_async(self):
        threading.Thread(target=self._install, daemon=True).start()

    def _install(self):
        try:
            if not self.zip_url:
                self.update_finished.emit(False, "No update package found")
                return
            work = tempfile.mkdtemp(prefix="livesprite_update_")
            zip_path = os.path.join(work, "update.zip")
            logger.info("Downloading update: %s", self.zip_url)
            with requests.get(self.zip_url, timeout=60, stream=True) as r:
                r.raise_for_status()
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
            extract = os.path.join(work, "extracted")
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(extract)
            # The zip may contain a single top-level folder - descend into it
            entries = os.listdir(extract)
            src = extract
            if len(entries) == 1 and os.path.isdir(
                    os.path.join(extract, entries[0])):
                src = os.path.join(extract, entries[0])

            if getattr(sys, "frozen", False):
                self._install_frozen(src)
            else:
                self._install_source(src)
        except (requests.RequestException, OSError, zipfile.BadZipFile) as e:
            logger.error("Update failed: %s", e)
            self.update_finished.emit(False, f"Update failed: {e}")

    def _copy_program_files(self, src, dst):
        """Copy update files over the installation, sparing personal data."""
        spare = {"config"}  # never touched; user assets are only added to
        for name in os.listdir(src):
            if name.lower() in spare:
                continue
            s = os.path.join(src, name)
            d = os.path.join(dst, name)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)

    def _install_source(self, src):
        self._copy_program_files(src, BASE_DIR)
        self.update_finished.emit(
            True, "Update installed - restart the program to finish")

    def _install_frozen(self, src):
        """Exe install: swap files via a helper batch after the app exits."""
        staged = os.path.join(BASE_DIR, "_update_staged")
        if os.path.isdir(staged):
            shutil.rmtree(staged, ignore_errors=True)
        os.makedirs(staged, exist_ok=True)
        self._copy_program_files(src, staged)

        helper = os.path.join(BASE_DIR, "_finish_update.bat")
        exe = sys.executable
        with open(helper, "w", encoding="ascii", errors="ignore") as f:
            f.write(
                "@echo off\r\n"
                "timeout /t 2 /nobreak >nul\r\n"
                f'robocopy "{staged}" "{BASE_DIR}" /E /IS /IT >nul\r\n'
                f'rmdir /S /Q "{staged}"\r\n'
                f'start "" "{exe}"\r\n'
                'del "%~f0"\r\n'
            )
        subprocess.Popen(
            ["cmd", "/c", helper],
            creationflags=subprocess.CREATE_NO_WINDOW,
            cwd=BASE_DIR,
        )
        self.update_finished.emit(
            True, "Update downloaded - the program will restart now")
