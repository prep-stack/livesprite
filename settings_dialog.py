#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sprite settings dialog.

Lets the user configure everything a sprite needs:
  * Twitch and YouTube channel + preferred platform
  * which animation to play when the streamer goes live
    (with an animated preview that follows the selection)
  * hide-when-offline
  * per-animation chance / direction / speed, each row showing an
    animated preview of that GIF
  * edge behavior and restricted screens
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication, QMovie
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QSpinBox, QTableWidget, QVBoxLayout,
    QWidget,
)

import theme
from sprite_model import DIRECTIONS, EDGE_BEHAVIORS

TABLE_PREVIEW_SIZE = 48   # preview height in the animations table
LIVE_PREVIEW_SIZE = 80    # preview height next to the live-animation picker


class GifPreviewLabel(QLabel):
    """A QLabel that plays a GIF scaled to a maximum height."""

    def __init__(self, max_height, parent=None):
        super().__init__(parent)
        self.max_height = max_height
        self.movie_ref = None
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(max_height)
        self.setMinimumWidth(max_height + 16)

    def set_gif(self, path):
        """Play the GIF at `path`, or clear the preview when path is None."""
        self.stop()
        if not path:
            self.clear()
            return
        movie = QMovie(path)
        if not movie.isValid():
            self.clear()
            return
        movie.jumpToFrame(0)
        size = movie.currentPixmap().size()
        if size.height() > 0:
            scaled = size.scaled(
                self.max_height * 2, self.max_height, Qt.KeepAspectRatio
            )
            movie.setScaledSize(scaled)
        self.movie_ref = movie
        self.setMovie(movie)
        movie.start()

    def set_speed(self, percent):
        """Set playback speed (100 = normal) on the running preview."""
        if self.movie_ref is not None:
            self.movie_ref.setSpeed(max(10, min(500, percent)))

    def stop(self):
        if self.movie_ref is not None:
            self.movie_ref.stop()
            self.movie_ref = None


class SpriteSettingsDialog(QDialog):
    """Edit one SpriteModel.  Writes back to the model on accept."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.setWindowTitle(f"Settings - {model.asset_dir}")
        self.resize(660, 720)
        theme.dark_title_bar(self)
        self._previews = []  # all GifPreviewLabel widgets, stopped on close

        layout = QVBoxLayout(self)

        # -- stream settings ------------------------------------------------
        stream_group = QGroupBox("Live stream tracking")
        form = QFormLayout(stream_group)

        self.twitch_edit = QLineEdit(model.twitch_channel)
        self.twitch_edit.setPlaceholderText("e.g. sodapoppin")
        form.addRow("Twitch channel:", self.twitch_edit)

        self.youtube_edit = QLineEdit(model.youtube_channel)
        self.youtube_edit.setPlaceholderText("e.g. @handle or channel URL")
        form.addRow("YouTube channel:", self.youtube_edit)

        self.kick_edit = QLineEdit(model.kick_channel)
        self.kick_edit.setPlaceholderText("e.g. xqc")
        form.addRow("Kick channel:", self.kick_edit)

        self.platform_combo = QComboBox()
        self.platform_combo.addItem("Twitch", "twitch")
        self.platform_combo.addItem("YouTube", "youtube")
        self.platform_combo.addItem("Kick", "kick")
        index = self.platform_combo.findData(model.preferred_platform)
        self.platform_combo.setCurrentIndex(max(index, 0))
        form.addRow("Preferred platform:", self.platform_combo)

        self.live_combo = QComboBox()
        self.live_combo.addItem("(none)", None)
        for name in model.animations:
            self.live_combo.addItem(name, name)
        if model.live_animation:
            idx = self.live_combo.findData(model.live_animation)
            if idx >= 0:
                self.live_combo.setCurrentIndex(idx)

        # Live-animation picker with an animated preview that follows it
        self.live_preview = GifPreviewLabel(LIVE_PREVIEW_SIZE)
        self._previews.append(self.live_preview)
        live_row = QHBoxLayout()
        live_row.addWidget(self.live_combo, 1)
        live_row.addWidget(self.live_preview)
        live_widget = QWidget()
        live_widget.setLayout(live_row)
        form.addRow("Live animation:", live_widget)

        self.live_combo.currentIndexChanged.connect(self._update_live_preview)
        self._update_live_preview()

        self.hide_offline_check = QCheckBox("Hide sprite while offline")
        self.hide_offline_check.setChecked(model.hide_when_offline)
        form.addRow(self.hide_offline_check)

        self.hide_notified_check = QCheckBox(
            "Hide again after the live notification was clicked"
        )
        self.hide_notified_check.setToolTip(
            "The sprite only shows up when the streamer goes live; after "
            "you double-click it (opening the stream) it hides again "
            "until the next stream.  Requires 'Hide sprite while offline'."
        )
        self.hide_notified_check.setChecked(
            model.hide_when_notified and model.hide_when_offline
        )
        self.hide_notified_check.setEnabled(model.hide_when_offline)
        form.addRow(self.hide_notified_check)

        # hide-when-notified only makes sense with hide-when-offline on
        self.hide_offline_check.toggled.connect(self._on_hide_offline_toggled)

        layout.addWidget(stream_group)

        # -- animation table --------------------------------------------------
        anim_group = QGroupBox(
            "Animations (chance %, direction, pixels/step, speed %)"
        )
        anim_layout = QVBoxLayout(anim_group)
        self.table = QTableWidget(len(model.animations), 5)
        self.table.setHorizontalHeaderLabels(
            ["Preview", "Chance", "Direction", "Pixels", "Speed %"]
        )
        self.table.setVerticalHeaderLabels(list(model.animations.keys()))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(
            TABLE_PREVIEW_SIZE + 8
        )
        self.table.setColumnWidth(0, TABLE_PREVIEW_SIZE * 2)

        for row, (name, anim) in enumerate(model.animations.items()):
            preview = GifPreviewLabel(TABLE_PREVIEW_SIZE)
            preview.set_gif(model.animation_path(name))
            self._previews.append(preview)
            self.table.setCellWidget(row, 0, preview)

            chance = QSpinBox()
            chance.setRange(0, 100)
            chance.setValue(anim.chance)
            self.table.setCellWidget(row, 1, chance)

            direction = QComboBox()
            for d in DIRECTIONS:
                direction.addItem(d)
            direction.setCurrentText(
                anim.direction if anim.direction in DIRECTIONS else "none"
            )
            self.table.setCellWidget(row, 2, direction)

            pixels = QSpinBox()
            pixels.setRange(0, 50)
            pixels.setValue(anim.pixels)
            self.table.setCellWidget(row, 3, pixels)

            speed = QSpinBox()
            speed.setRange(10, 500)
            speed.setSingleStep(10)
            speed.setValue(anim.speed)
            speed.setToolTip("Playback speed: 100 = normal, 200 = twice "
                             "as fast, 50 = half speed")
            # Preview follows the speed setting live
            speed.valueChanged.connect(
                lambda value, p=preview: p.set_speed(value)
            )
            preview.set_speed(anim.speed)
            self.table.setCellWidget(row, 4, speed)
        anim_layout.addWidget(self.table)
        layout.addWidget(anim_group)

        # -- screens / edges ---------------------------------------------------
        screen_group = QGroupBox("Screens and edges")
        screen_layout = QVBoxLayout(screen_group)

        edge_row = QHBoxLayout()
        self.edge_combo = QComboBox()
        for b in EDGE_BEHAVIORS:
            self.edge_combo.addItem(b)
        self.edge_combo.setCurrentText(model.edge_behavior)
        edge_row.addWidget(self.edge_combo)
        screen_layout.addLayout(edge_row)

        self.screen_checks = []
        for i, screen in enumerate(QGuiApplication.screens()):
            geo = screen.geometry()
            check = QCheckBox(
                f"Restrict screen {i} ({geo.width()}x{geo.height()} "
                f"at {geo.x()},{geo.y()})"
            )
            check.setChecked(i in model.restricted_screens)
            self.screen_checks.append(check)
            screen_layout.addWidget(check)

        layout.addWidget(screen_group)

        # -- buttons ------------------------------------------------------------
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        if ok_btn is not None:
            ok_btn.setProperty("accent", True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_hide_offline_toggled(self, checked):
        """Enable/disable the dependent hide-when-notified checkbox."""
        self.hide_notified_check.setEnabled(checked)
        if not checked:
            self.hide_notified_check.setChecked(False)

    def _update_live_preview(self):
        """Show the animation currently selected in the live-picker."""
        name = self.live_combo.currentData()
        if name:
            self.live_preview.set_gif(self.model.animation_path(name))
        else:
            self.live_preview.set_gif(None)

    def _stop_previews(self):
        for preview in self._previews:
            preview.stop()

    def accept(self):
        """Copy the UI values back into the model, then close."""
        m = self.model
        m.twitch_channel = self.twitch_edit.text().strip()
        m.youtube_channel = self.youtube_edit.text().strip()
        m.kick_channel = self.kick_edit.text().strip().lstrip("@")
        m.preferred_platform = self.platform_combo.currentData()
        m.live_animation = self.live_combo.currentData()
        m.hide_when_offline = self.hide_offline_check.isChecked()
        m.hide_when_notified = (self.hide_notified_check.isChecked()
                                and m.hide_when_offline)
        m.edge_behavior = self.edge_combo.currentText()
        m.restricted_screens = [
            i for i, c in enumerate(self.screen_checks) if c.isChecked()
        ]
        for row, anim in enumerate(m.animations.values()):
            anim.chance = self.table.cellWidget(row, 1).value()
            anim.direction = self.table.cellWidget(row, 2).currentText()
            anim.pixels = self.table.cellWidget(row, 3).value()
            anim.speed = self.table.cellWidget(row, 4).value()
        self._stop_previews()
        super().accept()

    def reject(self):
        self._stop_previews()
        super().reject()
