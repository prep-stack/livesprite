#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Windows autostart support.

Registers/unregisters the program in the current user's Run registry key
(HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run) so it starts
with the PC.  Works both as a script (uses pythonw.exe + main.py) and as
a frozen exe (uses LiveSprite.exe directly).  No admin rights needed.
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

APP_KEY = "LiveSprite"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _command():
    """The command line to register for autostart."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "main.py"
    )
    python = sys.executable
    # Prefer pythonw.exe so no console window appears at login
    pythonw = os.path.join(os.path.dirname(python), "pythonw.exe")
    if os.path.exists(pythonw):
        python = pythonw
    return f'"{python}" "{script}"'


def is_supported():
    return sys.platform == "win32"


def is_enabled():
    """True when an autostart entry for this app exists."""
    if not is_supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_KEY)
            return True
    except OSError:
        return False


def enable():
    """Register the program to start with Windows."""
    if not is_supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, APP_KEY, 0, winreg.REG_SZ, _command())
        logger.info("Autostart enabled: %s", _command())
        return True
    except OSError as e:
        logger.error("Could not enable autostart: %s", e)
        return False


def disable():
    """Remove the autostart registration."""
    if not is_supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, APP_KEY)
        logger.info("Autostart disabled")
    except FileNotFoundError:
        pass  # was not registered
    except OSError as e:
        logger.error("Could not disable autostart: %s", e)
        return False
    return True


def apply(enabled):
    """Enable or disable autostart to match the given setting."""
    if enabled:
        enable()
    else:
        disable()
