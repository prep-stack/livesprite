#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stream status service for Twitch and YouTube.

Uses the free DecAPI service (same as the old program):
  Twitch : https://decapi.me/twitch/uptime/<channel>
           -> "<channel> is offline" when offline, an uptime string when live.
  YouTube: two selectable methods (per sprite):
           * "decapi" (default): compare latest_video with and without
             no_livestream=1; different answers mean the channel is live.
           * "scrape": fetch https://www.youtube.com/<handle>/live with a
             browser User-Agent and look for '"isLive":true' in the HTML
             (guarding against '"isUpcoming":true' for scheduled streams).

All network requests run on a background thread; results are delivered to
the UI thread through a Qt signal.  The service also tracks per-channel
"notified" and "visited" flags:

  - notified: the live animation has been triggered for this live session
  - visited : the user clicked the sprite and opened the stream page

Both flags reset when a channel goes offline (and on app start, since the
service starts empty), so the user is notified again on the next stream.
"""

import logging
import random
import threading
import time
from urllib.parse import urlparse

import requests
from PyQt5.QtCore import QObject, pyqtSignal

from config import STREAM_CHECK_INTERVAL_S

logger = logging.getLogger(__name__)

# Realistic browser headers so YouTube/Kick don't block us as a bot.
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}
# Cookies that skip YouTube's EU cookie-consent wall, which would
# otherwise redirect the /live request to consent.youtube.com.
YOUTUBE_COOKIES = {"CONSENT": "YES+", "SOCS": "CAI"}

# Random +/- jitter (seconds) added to every poll interval so the
# requests don't land on an exact clockwork schedule (bot-friendly).
POLL_JITTER_S = 15


def parse_youtube_channel(channel_input):
    """Extract a channel handle/ID DecAPI understands from a URL or raw text."""
    if not channel_input:
        return ""
    channel_input = channel_input.strip()
    if not channel_input.startswith("http"):
        return channel_input
    try:
        parts = [p for p in urlparse(channel_input).path.split("/") if p]
        for i, part in enumerate(parts):
            if part.startswith("@"):
                return part
            if part in ("channel", "c", "user") and i + 1 < len(parts):
                return parts[i + 1]
        skip = {"live", "videos", "shorts", "streams", "about", "featured"}
        for part in parts:
            if part not in skip:
                return part
    except ValueError as e:
        logger.warning("Could not parse YouTube channel '%s': %s", channel_input, e)
    return channel_input


class StreamService(QObject):
    """Polls Twitch/YouTube channels in the background and caches status."""

    # Emitted on the UI thread: (platform, channel, is_live)
    status_changed = pyqtSignal(str, str, bool)

    # A live channel must look offline this many checks in a row before
    # we accept it as offline.  Protects against single flaky API answers
    # that would otherwise reset the notified/visited flags and replay
    # the live notification while the streamer never actually went down.
    OFFLINE_CONFIRMATIONS = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._channels = {}     # (platform, channel) -> subscriber count
        self._status = {}       # (platform, channel) -> bool (is live)
        self._notified = set()  # channels notified this live session
        self._visited = set()   # channels visited (clicked) this live session
        self._offline_seen = {}  # (platform, channel) -> consecutive offline count
        self._yt_method = {}    # (platform, channel) -> "decapi" or "scrape"
        self._session = requests.Session()
        self._stop = threading.Event()
        self._thread = None

    # -- subscriptions ------------------------------------------------------
    def track(self, platform, channel, youtube_method="decapi"):
        """Start tracking a channel (idempotent).

        `youtube_method` selects how YouTube channels are checked:
        "decapi" (default) or "scrape" (the channel's /live page).
        """
        key = self._key(platform, channel)
        if not key:
            return
        with self._lock:
            self._channels[key] = self._channels.get(key, 0) + 1
            if key[0] == "youtube":
                self._yt_method[key] = (
                    "scrape" if youtube_method == "scrape" else "decapi"
                )
        self._ensure_thread()

    def untrack(self, platform, channel):
        """Stop tracking a channel when no sprite uses it any more."""
        key = self._key(platform, channel)
        if not key:
            return
        with self._lock:
            if key in self._channels:
                self._channels[key] -= 1
                if self._channels[key] <= 0:
                    del self._channels[key]
                    self._status.pop(key, None)
                    self._yt_method.pop(key, None)

    # -- status queries (UI thread safe, never block) -------------------------
    def is_live(self, platform, channel):
        key = self._key(platform, channel)
        with self._lock:
            return self._status.get(key, False)

    def is_notified(self, platform, channel):
        key = self._key(platform, channel)
        with self._lock:
            return key in self._notified

    def mark_notified(self, platform, channel):
        key = self._key(platform, channel)
        with self._lock:
            self._notified.add(key)

    def is_visited(self, platform, channel):
        key = self._key(platform, channel)
        with self._lock:
            return key in self._visited

    def mark_visited(self, platform, channel):
        key = self._key(platform, channel)
        with self._lock:
            self._visited.add(key)

    # -- lifecycle -----------------------------------------------------------
    def start(self):
        self._ensure_thread()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _ensure_thread(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._poll_loop, name="stream-poll", daemon=True
            )
            self._thread.start()

    # -- polling (background thread) -------------------------------------------
    def _poll_loop(self):
        while not self._stop.is_set():
            with self._lock:
                keys = list(self._channels.keys())
            for key in keys:
                if self._stop.is_set():
                    return
                self._check_channel(key)
            # Sleep ~60s +/- random jitter so the checks don't run on an
            # exact clockwork schedule (looks less bot-like to servers).
            # Sleep in small slices so stop() reacts quickly.
            wait_s = STREAM_CHECK_INTERVAL_S + random.uniform(
                -POLL_JITTER_S, POLL_JITTER_S
            )
            for _ in range(max(2, int(wait_s * 2))):
                if self._stop.is_set():
                    return
                time.sleep(0.5)

    def _check_channel(self, key):
        platform, channel = key
        try:
            if platform == "twitch":
                is_live = self._check_twitch(channel)
            elif platform == "kick":
                is_live = self._check_kick(channel)
            else:
                with self._lock:
                    method = self._yt_method.get(key, "decapi")
                if method == "scrape":
                    is_live = self._check_youtube_scrape(channel)
                else:
                    is_live = self._check_youtube(channel)
        except requests.RequestException as e:
            logger.warning("Network error checking %s/%s: %s", platform, channel, e)
            return  # keep last known status on network problems

        with self._lock:
            first_check = key not in self._status
            was_live = self._status.get(key, False)

            # Debounce live -> offline: require several consecutive
            # offline answers before accepting that the stream ended.
            if was_live and not is_live:
                self._offline_seen[key] = self._offline_seen.get(key, 0) + 1
                if self._offline_seen[key] < self.OFFLINE_CONFIRMATIONS:
                    logger.info(
                        "%s/%s reported offline (%d/%d) - waiting for "
                        "confirmation before resetting",
                        platform, channel, self._offline_seen[key],
                        self.OFFLINE_CONFIRMATIONS,
                    )
                    return  # keep the live status for now
            else:
                self._offline_seen.pop(key, None)

            self._status[key] = is_live
            if was_live and not is_live:
                # Confirmed offline: reset flags so the next stream
                # notifies again
                self._offline_seen.pop(key, None)
                self._notified.discard(key)
                self._visited.discard(key)
                logger.info("%s/%s went offline - reset notified/visited",
                            platform, channel)
        # Also emit on the very first check so sprites can apply their
        # initial visibility (hide-when-offline) right after startup.
        if first_check or was_live != is_live:
            self.status_changed.emit(platform, channel, is_live)

    def _check_twitch(self, channel):
        url = f"https://decapi.me/twitch/uptime/{channel}"
        resp = self._session.get(url, timeout=10)
        if resp.status_code != 200:
            raise requests.RequestException(f"DecAPI status {resp.status_code}")
        text = resp.text.strip().lower()
        # Offline only on DecAPI's real offline/unknown-channel answers
        # ("<channel> is offline" / "... no user with the name ...").
        if "is offline" in text or "not found" in text or "no user" in text:
            return False
        # Error texts (server errors, rate limits...) must not count as
        # offline - raise so the last known status is kept instead.
        if "error" in text or not text:
            raise requests.RequestException(f"DecAPI error answer: {text!r}")
        # Anything else is an uptime string like "2 hours, 5 minutes"
        return True

    def _check_youtube(self, channel):
        handle = parse_youtube_channel(channel)
        base = f"https://decapi.me/youtube/latest_video?handle={handle}"
        with_live = self._session.get(base, timeout=10)
        without_live = self._session.get(base + "&no_livestream=1", timeout=10)
        if with_live.status_code != 200 or without_live.status_code != 200:
            raise requests.RequestException(
                f"DecAPI status {with_live.status_code}/{without_live.status_code}"
            )
        # Different answers => a livestream is the latest "video" => live now
        return with_live.text.strip() != without_live.text.strip()

    def _check_youtube_scrape(self, channel):
        """Check YouTube by scraping the channel's /live page.

        When a channel is live, youtube.com/<handle>/live serves (or
        redirects to) the watch page whose player data contains
        '"isLive":true'.  Scheduled premieres/streams also get a watch
        page but carry '"isUpcoming":true' instead, so those must not
        count as live.  Browser headers avoid the bot filter and the
        CONSENT/SOCS cookies skip the EU cookie-consent redirect.
        """
        handle = parse_youtube_channel(channel)
        if not handle.startswith("@") and not handle.startswith("UC"):
            handle = "@" + handle
        if handle.startswith("UC") and len(handle) >= 20:
            url = f"https://www.youtube.com/channel/{handle}/live"
        else:
            url = f"https://www.youtube.com/{handle}/live"
        resp = self._session.get(
            url, headers=BROWSER_HEADERS, cookies=YOUTUBE_COOKIES,
            timeout=15, allow_redirects=True,
        )
        if resp.status_code == 429:
            # Rate limited - back off by keeping the last known status.
            raise requests.RequestException(
                "YouTube rate limit (429 Too Many Requests)"
            )
        if resp.status_code == 404:
            return False  # channel does not exist -> treat as offline
        if resp.status_code != 200:
            raise requests.RequestException(
                f"YouTube /live status {resp.status_code}"
            )
        if "consent.youtube.com" in resp.url:
            # Consent wall instead of the channel page - can't tell the
            # status, keep the last known one.
            raise requests.RequestException(
                "YouTube consent wall blocked the /live page"
            )
        html = resp.text
        if '"isUpcoming":true' in html:
            return False  # scheduled stream/premiere, not live yet
        return '"isLive":true' in html

    def _check_kick(self, channel):
        """Check Kick via its public channel API.

        The endpoint returns JSON with a `livestream` object when the
        channel is currently broadcasting, or `livestream: null` when
        offline.  A browser-like User-Agent is needed so Kick's bot
        filter does not block the request.
        """
        url = f"https://kick.com/api/v1/channels/{channel}"
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/124.0 Safari/537.36"),
            "Accept": "application/json",
        }
        resp = self._session.get(url, headers=headers, timeout=10)
        if resp.status_code == 404:
            return False  # channel does not exist -> treat as offline
        if resp.status_code != 200:
            raise requests.RequestException(
                f"Kick API status {resp.status_code}"
            )
        try:
            data = resp.json()
        except ValueError as e:
            raise requests.RequestException(f"Kick API bad JSON: {e}")
        livestream = data.get("livestream")
        return bool(livestream)

    @staticmethod
    def _key(platform, channel):
        if not channel:
            return None
        platform = (platform or "twitch").lower().strip()
        channel = channel.lower().strip()
        return (platform, channel)
