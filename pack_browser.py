#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sprite pack browser dialog.

Lists every pack in the community repository with an animated preview,
name, creator, version and description.  Each row has one button whose
label depends on the pack's state:

  Install          - not installed yet
  Update (v1.1.0)  - installed from the repo, newer version available
  Installed        - up to date (disabled)

Downloads run in the background through PackService; the dialog stays
responsive and the row button shows progress.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QMovie
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget,
)

import theme
from pack_service import installed_pack_version, parse_version

PREVIEW_SIZE = 72


class PackRowWidget(QWidget):
    """One pack: animated preview + texts + install/update button."""

    def __init__(self, pack, on_install, parent=None):
        super().__init__(parent)
        self.pack = pack
        self.movie = None

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)

        preview = QLabel()
        preview.setFixedSize(PREVIEW_SIZE + 16, PREVIEW_SIZE)
        preview.setAlignment(Qt.AlignCenter)
        if pack.get("preview_local"):
            movie = QMovie(pack["preview_local"])
            if movie.isValid():
                movie.jumpToFrame(0)
                size = movie.currentPixmap().size()
                if size.height() > 0:
                    movie.setScaledSize(size.scaled(
                        PREVIEW_SIZE + 16, PREVIEW_SIZE, Qt.KeepAspectRatio
                    ))
                self.movie = movie
                preview.setMovie(movie)
                movie.start()
        row.addWidget(preview)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = QLabel(
            f"<b>{pack['name']}</b> "
            f"<span style='color:{theme.MUTED}'>v{pack['version']} "
            f"by {pack['creator']}</span>"
        )
        texts.addWidget(title)
        if pack.get("description"):
            desc = QLabel(pack["description"])
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {theme.MUTED};")
            texts.addWidget(desc)
        gif_count = sum(
            1 for path, _ in pack["files"] if path.lower().endswith(".gif")
        )
        count = QLabel(f"{gif_count} animation(s)")
        count.setStyleSheet(f"color: {theme.MUTED};")
        texts.addWidget(count)
        row.addLayout(texts, 1)

        self.button = QPushButton()
        self.button.setFixedWidth(130)
        self.button.clicked.connect(lambda: on_install(self))
        row.addWidget(self.button)

        self.refresh_state()

    def refresh_state(self):
        """Set the button label from the installed state on disk."""
        installed = installed_pack_version(self.pack["id"])
        if installed is None:
            self.button.setText("Install")
            self.button.setProperty("accent", True)
            self.button.setEnabled(True)
        elif parse_version(self.pack["version"]) > parse_version(installed):
            self.button.setText(f"Update (v{self.pack['version']})")
            self.button.setProperty("accent", True)
            self.button.setEnabled(True)
        else:
            self.button.setText("Installed")
            self.button.setProperty("accent", False)
            self.button.setEnabled(False)
        # Re-polish so the accent property change takes effect
        self.button.style().unpolish(self.button)
        self.button.style().polish(self.button)

    def set_busy(self):
        self.button.setText("Downloading...")
        self.button.setEnabled(False)

    def stop(self):
        if self.movie is not None:
            self.movie.stop()
            self.movie = None


class PackBrowserDialog(QDialog):
    """Browse, install and update community sprite packs."""

    def __init__(self, pack_service, parent=None):
        super().__init__(parent)
        self.packs = pack_service
        self.setWindowTitle("Browse sprite packs")
        self.resize(560, 520)
        theme.dark_title_bar(self)
        self._rows = []

        layout = QVBoxLayout(self)

        header = QLabel(
            "Community sprite packs - anyone can contribute at "
            "<a href='https://github.com/prep-stack/livesprite_gifs'>"
            "github.com/prep-stack/livesprite_gifs</a>"
        )
        header.setOpenExternalLinks(True)
        layout.addWidget(header)

        self.status_label = QLabel("Loading packs...")
        self.status_label.setStyleSheet(f"color: {theme.MUTED};")
        layout.addWidget(self.status_label)

        self.list = QListWidget(self)
        self.list.setSelectionMode(QListWidget.NoSelection)
        layout.addWidget(self.list, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._reload)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        buttons.addWidget(refresh_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        self.packs.packs_loaded.connect(self._on_packs_loaded)
        self.packs.install_finished.connect(self._on_install_finished)
        self._reload()

    def _reload(self):
        self.status_label.setText("Loading packs...")
        self.packs.load_packs_async()

    def _on_packs_loaded(self, ok, packs, error):
        for row in self._rows:
            row.stop()
        self._rows = []
        self.list.clear()
        if not ok:
            self.status_label.setText(f"Could not load packs: {error}")
            return
        if not packs:
            self.status_label.setText("No packs available yet")
            return
        self.status_label.setText(f"{len(packs)} pack(s) available")
        for pack in packs:
            row = PackRowWidget(pack, self._on_install_clicked)
            item = QListWidgetItem(self.list)
            item.setSizeHint(row.sizeHint())
            item.setFlags(Qt.NoItemFlags)
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
            self._rows.append(row)

    def _on_install_clicked(self, row):
        row.set_busy()
        self.status_label.setText(f"Downloading {row.pack['name']}...")
        self.packs.install_async(row.pack)

    def _on_install_finished(self, pack_id, ok, message):
        self.status_label.setText(message)
        for row in self._rows:
            if row.pack["id"] == pack_id:
                row.refresh_state()

    def _stop_previews(self):
        for row in self._rows:
            row.stop()

    def accept(self):
        self._stop_previews()
        super().accept()

    def reject(self):
        self._stop_previews()
        super().reject()
