#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Configuration helpers and constants for LiveSprite (clean rewrite).

Everything lives next to the application:
  new/assets/<sprite>/          - GIF files + settings.json per sprite
  new/config/session.json       - which sprites are open and where
"""

import os
import sys
import json
import logging

logger = logging.getLogger(__name__)

# Paths -----------------------------------------------------------------
if getattr(sys, "frozen", False):
    # Running as a PyInstaller exe: use the folder next to LiveSprite.exe
    # so assets/ and config/ stay editable real folders.
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
SESSION_FILE = os.path.join(CONFIG_DIR, "session.json")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
ICON_FILE = os.path.join(BASE_DIR, "soda.png")

# Constants -------------------------------------------------------------
APP_NAME = "LiveSprite"
MOVEMENT_INTERVAL_MS = 50          # ~20 movement steps per second
ANIMATION_SWITCH_CHANCE = 0.2      # 20% chance to switch animation per loop
STREAM_CHECK_INTERVAL_S = 60       # poll stream status every 60 seconds
DEFAULT_PIXELS = 5                 # default movement speed (pixels per step)
DEFAULT_CHANCE = 20                # default animation weight


def load_json(path, default=None):
    """Load a JSON file, returning `default` when missing or broken."""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read %s: %s", path, e)
    return default


def save_json(path, data):
    """Save data as pretty JSON, creating parent folders when needed."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except OSError as e:
        logger.error("Could not write %s: %s", path, e)
        return False
