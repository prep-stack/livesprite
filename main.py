#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LiveSprite (clean rewrite) - entry point.

Shows animated GIF sprites walking around the desktop, with Twitch and
YouTube live-stream notifications.  Run with:

    python main.py
"""

import logging
import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from config import APP_NAME, ICON_FILE
from main_window import MainWindow
from stream_service import StreamService
from tray import TrayIcon


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.info("%s starting", APP_NAME)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(ICON_FILE))
    # The app lives in the system tray: closing windows must not quit it
    app.setQuitOnLastWindowClosed(False)

    streams = StreamService()
    streams.start()

    window = MainWindow(streams)
    window.show()

    tray = TrayIcon(window)
    tray.show()

    # Safety net: on app quit and on Windows logoff/shutdown, save the
    # session while all active sprites are still registered in it.
    app.aboutToQuit.connect(window.save_session)
    try:
        app.commitDataRequest.connect(lambda _mgr: window.save_session())
    except AttributeError:
        pass  # not available on this platform/Qt build

    exit_code = app.exec_()
    streams.stop()
    logging.info("%s exiting", APP_NAME)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
