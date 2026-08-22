#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Manager window.

Two panels with animated GIF previews:
  * left  - all asset folders (available sprites)
  * right - active sprites currently on the desktop

Plus global actions (show all / hide all / restrict all to screens) that
are also reachable from the system tray icon.  Closing the window hides
it to the tray instead of quitting.

The set of active sprites and their positions is saved to
config/session.json and restored on the next start.
"""

import logging
import os
import sys
import webbrowser

from PyQt5.QtCore import QBuffer, QByteArray, QFileSystemWatcher, Qt, QSize, QTimer
from PyQt5.QtGui import QGuiApplication, QIcon, QMovie
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

import autostart
from config import (
    APP_NAME, ASSETS_DIR, ICON_FILE, SESSION_FILE, SETTINGS_FILE,
    load_json, save_json,
)
from updater import Updater
from version import VERSION
from sprite_model import SpriteModel, list_asset_dirs
from sprite_window import SpriteWindow
from settings_dialog import SpriteSettingsDialog

logger = logging.getLogger(__name__)

PREVIEW_SIZE = 48  # pixel height of animated previews in the lists


class PreviewItemWidget(QWidget):
    """List row with an animated GIF preview and the sprite name."""

    def __init__(self, asset_dir, subtitle="", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self.movie = None
        preview = QLabel(self)
        preview.setFixedSize(PREVIEW_SIZE + 12, PREVIEW_SIZE)
        preview.setAlignment(Qt.AlignCenter)

        gif_path = self._pick_preview_gif(asset_dir)
        if gif_path:
            # Load the GIF through a memory buffer so the file on disk is
            # not kept locked (allows deleting/replacing asset folders
            # while the manager is open).
            try:
                with open(gif_path, "rb") as f:
                    self._gif_data = QByteArray(f.read())
                self._gif_buffer = QBuffer(self._gif_data)
                self._gif_buffer.open(QBuffer.ReadOnly)
                self.movie = QMovie()
                self.movie.setDevice(self._gif_buffer)
                self.movie.setFormat(b"gif")
            except OSError:
                self.movie = None
            if self.movie is not None and self.movie.isValid():
                self.movie.jumpToFrame(0)
                size = self.movie.currentPixmap().size()
                if size.height() > 0:
                    scaled = size.scaled(
                        PREVIEW_SIZE + 12, PREVIEW_SIZE, Qt.KeepAspectRatio
                    )
                    self.movie.setScaledSize(scaled)
                preview.setMovie(self.movie)
                self.movie.start()
        layout.addWidget(preview)

        self.subtitle = subtitle  # raw subtitle text (used by tests/tools)
        # Make LIVE stand out in red
        subtitle_html = subtitle.replace(
            "LIVE", "<span style='color:#e91916;font-weight:bold'>LIVE</span>"
        )
        text = QLabel(
            f"<b>{asset_dir}</b>"
            + (f"<br><small>{subtitle_html}</small>" if subtitle else "")
        )
        layout.addWidget(text, 1)

    @staticmethod
    def _pick_preview_gif(asset_dir):
        """Prefer an idle GIF for the preview, else the first GIF."""
        model = SpriteModel(asset_dir)
        try:
            gifs = sorted(
                f for f in os.listdir(model.folder)
                if f.lower().endswith(".gif")
            )
        except OSError:
            return None
        if not gifs:
            return None
        idle = [g for g in gifs if "idle" in g.lower()]
        return model.animation_path(idle[0] if idle else gifs[0])

    def stop(self):
        if self.movie is not None:
            self.movie.stop()


class MainWindow(QMainWindow):
    """Simple sprite manager."""

    def __init__(self, stream_service):
        super().__init__()
        self.streams = stream_service
        self.sprite_windows = {}     # asset_dir -> SpriteWindow
        self.quit_requested = False  # set by the tray Quit action
        self.session = load_json(SESSION_FILE, default={}) or {}
        self.session.setdefault("sprites", {})
        # Remembered drag positions per sprite; survives remove/re-add
        self.session.setdefault("positions", {})

        # App settings (autostart on by default)
        self.app_settings = load_json(SETTINGS_FILE, default={}) or {}
        self.app_settings.setdefault("autostart", True)
        autostart.apply(self.app_settings["autostart"])

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(ICON_FILE))
        self.resize(680, 560)

        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # -- top bar: assets / info / support / reddit -----------------------
        top_bar = QHBoxLayout()
        assets_btn = QPushButton("Assets folder")
        assets_btn.setToolTip(
            "Open the assets folder - drop a folder of GIFs in there and "
            "the new sprite appears in the list automatically"
        )
        assets_btn.clicked.connect(self._open_assets_folder)
        info_btn = QPushButton("Info")
        info_btn.clicked.connect(self._show_info)
        support_btn = QPushButton("Support the program")
        support_btn.clicked.connect(
            lambda: webbrowser.open("https://ko-fi.com/livesprites")
        )
        reddit_btn = QPushButton("Reddit")
        reddit_btn.clicked.connect(
            lambda: webbrowser.open("https://www.reddit.com/r/livesprites/")
        )
        self.update_btn = QPushButton("Check for updates")
        self.update_btn.clicked.connect(self._on_update_clicked)
        top_bar.addWidget(assets_btn)
        top_bar.addWidget(info_btn)
        top_bar.addWidget(support_btn)
        top_bar.addWidget(reddit_btn)
        top_bar.addWidget(self.update_btn)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # Update machinery: quiet check at startup; the button flips to
        # "Update now" when a newer release exists.
        self._update_available = False
        self.updater = Updater(self)
        self.updater.check_finished.connect(self._on_update_check_finished)
        self.updater.update_finished.connect(self._on_update_finished)
        QTimer.singleShot(3000, self.updater.check_async)

        # -- two preview panels ------------------------------------------
        panels = QHBoxLayout()

        left_box = QVBoxLayout()
        left_box.addWidget(QLabel("<b>Assets</b> (double-click to add)"))
        self.asset_list = QListWidget(self)
        self.asset_list.itemDoubleClicked.connect(self._add_item)
        left_box.addWidget(self.asset_list)
        panels.addLayout(left_box)

        right_box = QVBoxLayout()
        right_box.addWidget(
            QLabel("<b>Active gifs</b> (double-click to remove)")
        )
        self.active_list = QListWidget(self)
        self.active_list.itemDoubleClicked.connect(self._remove_item)
        right_box.addWidget(self.active_list)
        panels.addLayout(right_box)

        layout.addLayout(panels)

        # -- per-sprite buttons --------------------------------------------
        buttons = QHBoxLayout()
        add_btn = QPushButton("Add →")
        add_btn.clicked.connect(self._add_selected)
        remove_btn = QPushButton("← Remove")
        remove_btn.clicked.connect(self._remove_selected)
        settings_btn = QPushButton("Settings...")
        settings_btn.clicked.connect(self._edit_selected)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_lists)
        buttons.addWidget(add_btn)
        buttons.addWidget(remove_btn)
        buttons.addWidget(settings_btn)
        buttons.addWidget(refresh_btn)
        layout.addLayout(buttons)

        # -- global actions -----------------------------------------------
        global_buttons = QHBoxLayout()
        show_all_btn = QPushButton("Show all")
        show_all_btn.clicked.connect(self.show_all_sprites)
        hide_all_btn = QPushButton("Hide all")
        hide_all_btn.clicked.connect(self.hide_all_sprites)
        restrict_btn = QPushButton("Restrict all...")
        restrict_btn.clicked.connect(self._show_restrict_menu)
        self._restrict_btn = restrict_btn
        global_buttons.addWidget(show_all_btn)
        global_buttons.addWidget(hide_all_btn)
        global_buttons.addWidget(restrict_btn)
        layout.addLayout(global_buttons)

        # -- app options ----------------------------------------------------
        self.autostart_check = QCheckBox("Start with Windows")
        self.autostart_check.setChecked(self.app_settings["autostart"])
        self.autostart_check.toggled.connect(self._on_autostart_toggled)
        layout.addWidget(self.autostart_check)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.streams.status_changed.connect(self._on_stream_status)

        # Auto-refresh the asset list when the assets folder changes
        # (new sprite folders dropped in, folders removed, GIFs added).
        # A short debounce timer avoids refreshing many times while
        # Windows is still copying files.
        os.makedirs(ASSETS_DIR, exist_ok=True)
        self._fs_watcher = QFileSystemWatcher(self)
        self._fs_watcher.addPath(ASSETS_DIR)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self._on_assets_changed)
        self._fs_watcher.directoryChanged.connect(
            lambda _path: self._refresh_timer.start()
        )

        self.refresh_lists()
        self._restore_session()

    # -- list handling ------------------------------------------------------
    def refresh_lists(self):
        self._fill_list(self.asset_list, list_asset_dirs(), active=False)
        self._fill_list(
            self.active_list, list(self.sprite_windows.keys()), active=True
        )

    def _fill_list(self, list_widget, asset_dirs, active):
        # Stop old preview movies before clearing
        for i in range(list_widget.count()):
            widget = list_widget.itemWidget(list_widget.item(i))
            if isinstance(widget, PreviewItemWidget):
                widget.stop()
        list_widget.clear()

        for asset_dir in asset_dirs:
            subtitle = ""
            if active and asset_dir in self.sprite_windows:
                window = self.sprite_windows[asset_dir]
                chan = window.model.stream_channel()
                if chan:
                    live = self.streams.is_live(*chan)
                    subtitle = f"{chan[1]} ({chan[0]}) - " + (
                        "LIVE" if live else "offline"
                    )
                if not window.isVisible():
                    subtitle = (subtitle + " [hidden]").strip()
            elif not active and asset_dir in self.sprite_windows:
                subtitle = "on desktop"

            item = QListWidgetItem()
            item.setData(Qt.UserRole, asset_dir)
            widget = PreviewItemWidget(asset_dir, subtitle)
            item.setSizeHint(widget.sizeHint())
            list_widget.addItem(item)
            list_widget.setItemWidget(item, widget)

    @staticmethod
    def _selected_in(list_widget):
        item = list_widget.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _selected_asset(self):
        """Selection from whichever panel has one (active panel wins)."""
        return (self._selected_in(self.active_list)
                or self._selected_in(self.asset_list))

    def _add_item(self, item):
        asset = item.data(Qt.UserRole)
        if asset not in self.sprite_windows:
            self.show_sprite(asset)
        self.refresh_lists()

    def _remove_item(self, item):
        asset = item.data(Qt.UserRole)
        if asset in self.sprite_windows:
            self.sprite_windows[asset].request_close()
        self.refresh_lists()

    def _add_selected(self):
        asset = self._selected_in(self.asset_list)
        if asset and asset not in self.sprite_windows:
            self.show_sprite(asset)
            self.refresh_lists()

    def _remove_selected(self):
        asset = self._selected_in(self.active_list)
        if asset and asset in self.sprite_windows:
            self.sprite_windows[asset].request_close()
            self.refresh_lists()

    # -- global actions -------------------------------------------------------
    def show_all_sprites(self):
        """Make every active sprite visible again."""
        for window in self.sprite_windows.values():
            window.show()
        self.refresh_lists()
        logger.info("Showed all active sprites")

    def hide_all_sprites(self):
        """Hide every active sprite (stays active, keeps tracking streams)."""
        for window in self.sprite_windows.values():
            window.hide()
        self.refresh_lists()
        logger.info("Hid all active sprites")

    def common_restricted_screens(self):
        """Screen indices restricted in ALL active sprites (for checkboxes)."""
        models = [w.model for w in self.sprite_windows.values()]
        if not models:
            return set()
        common = set(models[0].restricted_screens)
        for m in models[1:]:
            common &= set(m.restricted_screens)
        return common

    def set_screen_restriction_all(self, screen_index, restricted):
        """Add/remove one restricted screen on every active sprite and save."""
        for window in self.sprite_windows.values():
            model = window.model
            current = set(model.restricted_screens)
            if restricted:
                current.add(screen_index)
            else:
                current.discard(screen_index)
            model.restricted_screens = sorted(current)
            model.save()
            window.ensure_on_allowed_screen()
        logger.info(
            "Screen %d %s for all active sprites",
            screen_index, "restricted" if restricted else "allowed",
        )

    def clear_screen_restrictions_all(self):
        """Remove all screen restrictions from every active sprite."""
        for window in self.sprite_windows.values():
            window.model.restricted_screens = []
            window.model.save()
        logger.info("Cleared screen restrictions for all active sprites")

    def _show_restrict_menu(self):
        """Popup with per-screen restriction checkboxes (same as tray)."""
        menu = QMenu(self)
        restricted = self.common_restricted_screens()
        for i, screen in enumerate(QGuiApplication.screens()):
            geo = screen.geometry()
            action = menu.addAction(
                f"Avoid screen {i} ({geo.width()}x{geo.height()})"
            )
            action.setCheckable(True)
            action.setChecked(i in restricted)
            action.toggled.connect(
                lambda checked, idx=i:
                self.set_screen_restriction_all(idx, checked)
            )
        menu.addSeparator()
        clear = menu.addAction("Clear all screen restrictions")
        clear.triggered.connect(self.clear_screen_restrictions_all)
        menu.exec_(self._restrict_btn.mapToGlobal(
            self._restrict_btn.rect().bottomLeft()
        ))

    def show_sprite(self, asset_dir, position=None):
        """Create and show the sprite window for an asset folder.

        Spawn position priority:
          1. an explicit `position` argument (session restore / reload)
          2. the last spot the user dragged this sprite to (remembered
             even after the sprite was removed and re-added)
          3. screen center for brand-new sprites
        """
        if asset_dir in self.sprite_windows:
            return
        model = SpriteModel(asset_dir)
        if not model.load():
            logger.error("Could not load sprite: %s", asset_dir)
            return
        window = SpriteWindow(
            model, self.streams,
            on_closed=self._on_sprite_closed,
            on_moved=self._on_sprite_moved,
        )
        if position is None or position[0] is None or position[1] is None:
            remembered = self.session["positions"].get(asset_dir)
            if remembered:
                position = (remembered.get("x"), remembered.get("y"))
        if position and position[0] is not None and position[1] is not None:
            window.move(position[0], position[1])
        window.show()
        window.ensure_on_allowed_screen()
        # Apply hide-when-offline etc. against the current cached stream
        # status right away - a newly created window would otherwise wait
        # for a status *change* signal that may never come.
        window.apply_visibility()
        self.sprite_windows[asset_dir] = window
        self.session["sprites"][asset_dir] = {
            "x": window.x(), "y": window.y(),
        }
        self._save_session()

    def _on_sprite_closed(self, asset_dir, deliberate=True):
        self.sprite_windows.pop(asset_dir, None)
        if deliberate:
            # Only a user removal forgets the sprite.  When the window is
            # closed by the OS (shutdown/logoff) or by an app quit, the
            # sprite stays in the session and respawns on the next start.
            self.session["sprites"].pop(asset_dir, None)
            self._save_session()
        # NOTE: the remembered drag position is always kept so the sprite
        # comes back at the same spot when re-added later.
        self.refresh_lists()

    def _on_sprite_moved(self, asset_dir, x, y):
        """The user dragged a sprite - remember that spot permanently."""
        self.session["sprites"][asset_dir] = {"x": x, "y": y}
        self.session["positions"][asset_dir] = {"x": x, "y": y}
        self._save_session()

    # -- settings -----------------------------------------------------------
    def _edit_selected(self):
        asset = self._selected_asset()
        if not asset:
            return
        model = SpriteModel(asset)
        if not model.load():
            return
        dialog = SpriteSettingsDialog(model, self)
        if dialog.exec_():
            model.save()
            # Reload the sprite if it is currently shown
            if asset in self.sprite_windows:
                pos = self.sprite_windows[asset].pos()
                self.sprite_windows[asset].request_close()
                self.show_sprite(asset, position=(pos.x(), pos.y()))
            self.refresh_lists()

    def _open_assets_folder(self):
        """Open the assets folder in Windows Explorer."""
        os.makedirs(ASSETS_DIR, exist_ok=True)
        os.startfile(ASSETS_DIR)
        logger.info("Opened assets folder: %s", ASSETS_DIR)

    # -- updates ------------------------------------------------------------
    def _on_update_clicked(self):
        if self._update_available:
            self.update_btn.setEnabled(False)
            self.update_btn.setText("Updating...")
            self.updater.install_async()
        else:
            self.update_btn.setEnabled(False)
            self.update_btn.setText("Checking...")
            self.updater.check_async()

    def _on_update_check_finished(self, available, latest, zip_url):
        self._update_available = available
        self.update_btn.setEnabled(True)
        if available:
            self.update_btn.setText(f"Update now (v{latest})")
            self.status_label.setText(
                f"A new version v{latest} is available - "
                f"you have v{VERSION}"
            )
        else:
            self.update_btn.setText("Check for updates")
            # Only report "up to date" when the user clicked the button
            if self.isVisible() and self.update_btn.hasFocus():
                self.status_label.setText(
                    f"You are up to date (v{VERSION})"
                )

    def _on_update_finished(self, success, message):
        self.status_label.setText(message)
        if success and getattr(sys, "frozen", False):
            # helper .bat swaps files and restarts after we exit
            self.quit_requested = True
            QApplication.quit()
        else:
            self.update_btn.setEnabled(True)
            self.update_btn.setText("Check for updates")
            self._update_available = False

    def _show_info(self):
        """Show a small dialog about how the program works."""
        QMessageBox.information(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b><br><br>"
            "Animated GIF sprites that walk around your desktop and "
            "notify you when your favorite streamers go live.<br><br>"
            "<b>How live status is checked</b><br>"
            "&bull; <b>Twitch</b> and <b>YouTube</b> are checked through "
            "the free <a href='https://decapi.me'>DecAPI</a> service.<br>"
            "&bull; <b>Kick</b> is checked with a basic HTTP GET request "
            "to Kick's public channel API.<br><br>"
            "Each tracked channel is checked about once per minute. "
            "No accounts or API keys are needed.<br><br>"
            "Sprites live in the <i>assets</i> folder - one folder of "
            "GIFs per sprite. Double-click a sprite on the desktop to "
            "open its stream when live.",
        )

    def _on_assets_changed(self):
        """The assets folder changed on disk - refresh the lists."""
        logger.info("Assets folder changed, refreshing lists")
        self.refresh_lists()
        # Re-add the watch path in case the folder was replaced
        if ASSETS_DIR not in self._fs_watcher.directories():
            self._fs_watcher.addPath(ASSETS_DIR)

    # -- app options ----------------------------------------------------------
    def _on_autostart_toggled(self, checked):
        self.app_settings["autostart"] = checked
        save_json(SETTINGS_FILE, self.app_settings)
        autostart.apply(checked)
        logger.info("Autostart %s", "enabled" if checked else "disabled")

    # -- session ------------------------------------------------------------
    def _restore_session(self):
        for asset_dir, info in dict(self.session["sprites"]).items():
            self.show_sprite(
                asset_dir, position=(info.get("x"), info.get("y"))
            )
        self.refresh_lists()

    def _save_session(self):
        save_json(SESSION_FILE, self.session)

    def save_session(self):
        """Public save used by aboutToQuit / Windows logoff handlers."""
        self._save_session()

    # -- stream status display -----------------------------------------------
    def _on_stream_status(self, platform, channel, is_live):
        state = "LIVE" if is_live else "offline"
        self.status_label.setText(f"{channel} ({platform}) is now {state}")
        # Rebuild the lists so the LIVE/offline subtitle under each
        # active gif reflects the new status immediately.
        self.refresh_lists()

    # -- shutdown --------------------------------------------------------------
    def closeEvent(self, event):
        if not self.quit_requested:
            # Hide to the system tray instead of quitting
            event.ignore()
            self.hide()
            return
        # Real quit (from the tray menu)
        self._save_session()
        for window in list(self.sprite_windows.values()):
            window.on_closed = None  # keep session entries on app exit
            window.close()
        event.accept()
