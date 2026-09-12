#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sprite model.

A sprite is a folder inside assets/ containing GIF files and an optional
settings.json.  Each GIF is an animation with a weight (chance), a movement
direction and a speed in pixels per step.
"""

import os
import logging
from dataclasses import dataclass

from config import ASSETS_DIR, DEFAULT_CHANCE, DEFAULT_PIXELS, load_json, save_json

logger = logging.getLogger(__name__)

# direction name -> (dx, dy) unit vector
DIRECTIONS = {
    "none": (0, 0),
    "left": (-1, 0),
    "right": (1, 0),
    "up": (0, -1),
    "down": (0, 1),
    "up_left": (-1, -1),
    "up_right": (1, -1),
    "down_left": (-1, 1),
    "down_right": (1, 1),
}

EDGE_BEHAVIORS = ("wrap", "bounce", "stop")


@dataclass
class Animation:
    """A single GIF animation belonging to a sprite."""
    filename: str
    chance: int = DEFAULT_CHANCE       # weight used for random selection
    direction: str = "none"            # key of DIRECTIONS
    pixels: int = DEFAULT_PIXELS       # movement speed in pixels per step
    speed: int = 100                   # playback speed percentage (100 = normal)

    def delta(self):
        """Return the (dx, dy) movement for one step of this animation."""
        ux, uy = DIRECTIONS.get(self.direction, (0, 0))
        return ux * self.pixels, uy * self.pixels

    def to_dict(self):
        return {
            "chance": self.chance,
            "direction": self.direction,
            "pixels": self.pixels,
            "speed": self.speed,
        }


def _infer_direction(filename):
    """Guess a movement direction from the GIF filename.

    Used only when a sprite has no settings.json yet, so freshly dropped-in
    asset folders walk around sensibly out of the box.
    """
    name = filename.lower()
    if not any(w in name for w in ("run", "walk", "move")):
        return "none"
    has_left = "left" in name
    has_right = "right" in name
    has_up = "up" in name
    has_down = "down" in name
    if has_left and has_up:
        return "up_left"
    if has_right and has_up:
        return "up_right"
    if has_left and has_down:
        return "down_left"
    if has_right and has_down:
        return "down_right"
    if has_left:
        return "left"
    if has_right:
        return "right"
    return "none"


class SpriteModel:
    """Configuration and animation list for one sprite (asset folder)."""

    def __init__(self, asset_dir):
        self.asset_dir = asset_dir           # folder name inside assets/
        self.animations = {}                 # filename -> Animation
        self.live_animation = None           # animation shown when live
        self.twitch_channel = ""
        self.youtube_channel = ""
        self.kick_channel = ""
        self.preferred_platform = "twitch"   # "twitch", "youtube" or "kick"
        # How the YouTube channel is checked: "scrape" (default, fetches
        # the channel's /live page directly - most reliable) or "decapi".
        self.youtube_check_method = "scrape"
        self.hide_when_offline = False
        # Hide again after the live notification was clicked (visited);
        # only takes effect when hide_when_offline is also enabled.
        self.hide_when_notified = False
        self.edge_behavior = "wrap"          # wrap / bounce / stop
        # Keep the sprite above other windows (re-asserted periodically);
        # toggleable from the sprite's right-click menu.
        self.always_on_top = True
        self.allow_multi_screen = True
        self.restricted_screens = []         # screen indices the sprite avoids

    # -- paths ----------------------------------------------------------
    @property
    def folder(self):
        return os.path.join(ASSETS_DIR, self.asset_dir)

    @property
    def settings_path(self):
        return os.path.join(self.folder, "settings.json")

    def animation_path(self, filename):
        return os.path.join(self.folder, filename)

    def icon_path(self):
        """First PNG in the folder, used as an icon in the manager list."""
        try:
            for name in sorted(os.listdir(self.folder)):
                if name.lower().endswith(".png"):
                    return os.path.join(self.folder, name)
        except OSError:
            pass
        return None

    # -- persistence ------------------------------------------------------
    def load(self):
        """Scan the folder for GIFs and apply settings.json when present.

        Returns True when at least one GIF animation was found.
        """
        if not os.path.isdir(self.folder):
            logger.error("Asset folder not found: %s", self.folder)
            return False

        gifs = sorted(
            f for f in os.listdir(self.folder) if f.lower().endswith(".gif")
        )
        if not gifs:
            logger.error("No GIF files in: %s", self.folder)
            return False

        data = load_json(self.settings_path, default={}) or {}
        saved_anims = data.get("animations", {})

        self.animations = {}
        for gif in gifs:
            saved = saved_anims.get(gif, {})
            self.animations[gif] = Animation(
                filename=gif,
                chance=int(saved.get("chance", DEFAULT_CHANCE)),
                direction=saved.get("direction", _infer_direction(gif)),
                pixels=int(saved.get("pixels", DEFAULT_PIXELS)),
                speed=int(saved.get("speed", 100)),
            )

        self.live_animation = data.get("live_animation")
        if self.live_animation not in self.animations:
            self.live_animation = None
        self.twitch_channel = data.get("twitch_channel") or ""
        self.youtube_channel = data.get("youtube_channel") or ""
        self.kick_channel = data.get("kick_channel") or ""
        self.preferred_platform = data.get("preferred_platform", "twitch")
        self.youtube_check_method = data.get("youtube_check_method", "scrape")
        if self.youtube_check_method not in ("decapi", "scrape"):
            self.youtube_check_method = "scrape"
        self.hide_when_offline = bool(data.get("hide_when_offline", False))
        self.hide_when_notified = bool(
            data.get("hide_when_notified", False)
        ) and self.hide_when_offline
        self.edge_behavior = data.get("edge_behavior", "wrap")
        if self.edge_behavior not in EDGE_BEHAVIORS:
            self.edge_behavior = "wrap"
        self.always_on_top = bool(data.get("always_on_top", True))
        self.allow_multi_screen = bool(data.get("allow_multi_screen", True))
        self.restricted_screens = [
            int(i) for i in data.get("restricted_screens", [])
        ]
        return True

    def save(self):
        """Write the sprite settings to its settings.json."""
        data = {
            "animations": {n: a.to_dict() for n, a in self.animations.items()},
            "live_animation": self.live_animation,
            "twitch_channel": self.twitch_channel,
            "youtube_channel": self.youtube_channel,
            "kick_channel": self.kick_channel,
            "preferred_platform": self.preferred_platform,
            "youtube_check_method": self.youtube_check_method,
            "hide_when_offline": self.hide_when_offline,
            "hide_when_notified": self.hide_when_notified,
            "edge_behavior": self.edge_behavior,
            "always_on_top": self.always_on_top,
            "allow_multi_screen": self.allow_multi_screen,
            "restricted_screens": self.restricted_screens,
        }
        return save_json(self.settings_path, data)

    # -- stream helpers ---------------------------------------------------
    def stream_channel(self):
        """Return (platform, channel) for the preferred platform, or None."""
        if self.preferred_platform == "youtube" and self.youtube_channel:
            return "youtube", self.youtube_channel
        if self.preferred_platform == "kick" and self.kick_channel:
            return "kick", self.kick_channel
        if self.twitch_channel:
            return "twitch", self.twitch_channel
        if self.youtube_channel:
            return "youtube", self.youtube_channel
        if self.kick_channel:
            return "kick", self.kick_channel
        return None

    def stream_url(self):
        """URL opened when the sprite is double-clicked while live."""
        chan = self.stream_channel()
        if not chan:
            return None
        platform, channel = chan
        if platform == "twitch":
            return f"https://www.twitch.tv/{channel}"
        if platform == "kick":
            return f"https://kick.com/{channel}"
        if channel.startswith("http"):
            return channel
        if channel.startswith("@"):
            return f"https://www.youtube.com/{channel}/live"
        return f"https://www.youtube.com/@{channel}/live"


def list_asset_dirs():
    """Return the names of all asset folders that contain at least one GIF."""
    result = []
    try:
        for name in sorted(os.listdir(ASSETS_DIR)):
            folder = os.path.join(ASSETS_DIR, name)
            if os.path.isdir(folder):
                if any(f.lower().endswith(".gif") for f in os.listdir(folder)):
                    result.append(name)
    except OSError as e:
        logger.error("Cannot list assets dir: %s", e)
    return result
