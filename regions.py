#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Global restricted areas ("no-go zones" for sprites).

Rectangular desktop regions - drawn with the snipping-tool-style picker -
that every sprite must stay out of, e.g. a webcam corner or a stream
chat.  Global by design (they describe the user's desktop, not one
sprite) and stored in their own file config/regions.json so they survive
program updates (config/ is never touched by the updater) and cannot
clash with the app settings file.

Coordinates are global virtual-desktop coordinates (can span monitors).
"""

import logging
import os

from PyQt5.QtCore import QRect

from config import CONFIG_DIR, load_json, save_json

logger = logging.getLogger(__name__)

REGIONS_FILE = os.path.join(CONFIG_DIR, "regions.json")

MIN_SIZE = 20  # ignore accidental selections smaller than this (px)

_cache = None   # list of {"x", "y", "w", "h"} dicts


def _load():
    global _cache
    if _cache is None:
        data = load_json(REGIONS_FILE, default=[]) or []
        _cache = []
        for d in data:
            try:
                x, y = int(d["x"]), int(d["y"])
                w, h = int(d["w"]), int(d["h"])
            except (KeyError, TypeError, ValueError):
                continue
            if w >= MIN_SIZE and h >= MIN_SIZE:
                _cache.append({"x": x, "y": y, "w": w, "h": h})
    return _cache


def _save():
    save_json(REGIONS_FILE, _cache or [])


def all_regions():
    """List of region dicts (do not mutate)."""
    return list(_load())


def rects():
    """The regions as QRect objects (global coordinates)."""
    return [QRect(d["x"], d["y"], d["w"], d["h"]) for d in _load()]


def count():
    return len(_load())


def add(rect):
    """Add a region from a QRect; returns True when accepted."""
    rect = rect.normalized()
    if rect.width() < MIN_SIZE or rect.height() < MIN_SIZE:
        return False
    _load().append({
        "x": rect.x(), "y": rect.y(),
        "w": rect.width(), "h": rect.height(),
    })
    _save()
    logger.info("Added restricted area %dx%d at %d,%d",
                rect.width(), rect.height(), rect.x(), rect.y())
    return True


def remove(index):
    """Delete the region at `index`; returns True when it existed."""
    regions = _load()
    if 0 <= index < len(regions):
        gone = regions.pop(index)
        _save()
        logger.info("Removed restricted area %s", gone)
        return True
    return False


def clear():
    global _cache
    _cache = []
    _save()
    logger.info("Cleared all restricted areas")


def reload():
    """Drop the cache (used by tests)."""
    global _cache
    _cache = None
