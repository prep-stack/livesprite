#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
System tray icon.

Puts LiveSprite in the notification area (hidden icons) with a right-click
menu of quick actions:

  * Open Manager
  * Show all active gifs / Hide all active gifs
  * Restrict all to screen (checkable, one entry per monitor)
  * Clear all screen restrictions
  * Quit

Closing the manager window hides it to the tray; clicking the tray icon
brings it back.
"""

import logging

from PyQt5.QtGui import QGuiApplication, QIcon
from PyQt5.QtWidgets import QAction, QApplication, QMenu, QSystemTrayIcon

from config import APP_NAME, ICON_FILE

logger = logging.getLogger(__name__)


class TrayIcon(QSystemTrayIcon):
    """Tray icon with global sprite controls."""

    def __init__(self, main_window, parent=None):
        super().__init__(QIcon(ICON_FILE), parent)
        self.main_window = main_window
        self.setToolTip(APP_NAME)

        self.menu = QMenu()

        open_action = QAction("Open Manager", self.menu)
        open_action.triggered.connect(self._open_manager)
        self.menu.addAction(open_action)
        self.menu.addSeparator()

        show_all = QAction("Show all active gifs", self.menu)
        show_all.triggered.connect(main_window.show_all_sprites)
        self.menu.addAction(show_all)

        hide_all = QAction("Hide all active gifs", self.menu)
        hide_all.triggered.connect(main_window.hide_all_sprites)
        self.menu.addAction(hide_all)

        # Screen restriction submenu - rebuilt each time it opens so it
        # always matches the current monitors and sprite settings.
        self.restrict_menu = QMenu("Restrict all active gifs", self.menu)
        self.restrict_menu.aboutToShow.connect(self._rebuild_restrict_menu)
        self.menu.addMenu(self.restrict_menu)

        self.menu.addSeparator()
        quit_action = QAction("Quit", self.menu)
        quit_action.triggered.connect(self._quit)
        self.menu.addAction(quit_action)

        self.setContextMenu(self.menu)
        self.activated.connect(self._on_activated)

    # -- actions -----------------------------------------------------------
    def _open_manager(self):
        self.main_window.showNormal()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _on_activated(self, reason):
        # Left click / double click opens the manager
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._open_manager()

    def _rebuild_restrict_menu(self):
        self.restrict_menu.clear()
        restricted = self.main_window.common_restricted_screens()
        for i, screen in enumerate(QGuiApplication.screens()):
            geo = screen.geometry()
            action = QAction(
                f"Avoid screen {i} ({geo.width()}x{geo.height()})",
                self.restrict_menu,
            )
            action.setCheckable(True)
            action.setChecked(i in restricted)
            action.toggled.connect(
                lambda checked, idx=i:
                self.main_window.set_screen_restriction_all(idx, checked)
            )
            self.restrict_menu.addAction(action)
        self.restrict_menu.addSeparator()
        clear = QAction("Clear all screen restrictions", self.restrict_menu)
        clear.triggered.connect(self.main_window.clear_screen_restrictions_all)
        self.restrict_menu.addAction(clear)

    def _quit(self):
        self.main_window.quit_requested = True
        self.main_window.close()
        QApplication.quit()
