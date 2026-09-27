#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Snipping-tool-style region picker + "show restricted areas" overlays.

RegionPickerOverlay: a fullscreen translucent window covering the whole
virtual desktop (all monitors).  The screen dims, the cursor becomes a
crosshair and the user drags a rectangle; releasing the mouse confirms,
Esc cancels.  The chosen rect is reported in global desktop coordinates
through the `region_picked` callback.

RegionDisplayOverlay: one borderless red overlay per saved region shown
by the "Show restricted areas" toggle, with an index label and a small
X button that deletes the region.
"""

import logging

from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PyQt5.QtWidgets import QPushButton, QWidget

import theme

logger = logging.getLogger(__name__)


def virtual_desktop_rect():
    """Bounding rect of all screens (global coordinates)."""
    combined = QRect()
    for screen in QGuiApplication.screens():
        combined = combined.united(screen.geometry())
    return combined


class RegionPickerOverlay(QWidget):
    """Dim the desktop and let the user drag out one rectangle."""

    def __init__(self, region_picked, cancelled=None):
        super().__init__(None)
        self.region_picked = region_picked  # callback(QRect global)
        self.cancelled = cancelled          # callback() or None
        self._origin = None                 # QPoint (global) or None
        self._current = None                # QPoint (global) or None

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.setGeometry(virtual_desktop_rect())

    def open(self):
        self.show()
        self.raise_()
        self.activateWindow()  # needed so Esc reaches keyPressEvent

    # -- painting -----------------------------------------------------------
    def paintEvent(self, _event):
        painter = QPainter(self)
        dim = QColor(0, 0, 0, 100)  # the grayish tint
        selection = self._selection_rect()
        if selection is None:
            painter.fillRect(self.rect(), dim)
        else:
            # Dim everything except the selection
            local = QRect(selection.topLeft() - self.geometry().topLeft(),
                          selection.size())
            for part in self._surrounding(local):
                painter.fillRect(part, dim)
            painter.fillRect(local, QColor(124, 92, 255, 40))
            pen = QPen(QColor(theme.ACCENT), 2)
            painter.setPen(pen)
            painter.drawRect(local)
            # Size label near the selection
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            painter.setPen(QColor(theme.TEXT))
            painter.drawText(
                local.adjusted(0, -26, 0, 0).topLeft() + QPoint(2, 18),
                f"{selection.width()} x {selection.height()}",
            )
        # Instructions banner
        painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
        text = ("Drag to select an area sprites must avoid  -  "
                "Esc to cancel")
        banner = QRect(0, 24, self.width(), 36)
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(banner, Qt.AlignHCenter | Qt.AlignVCenter, text)

    def _surrounding(self, r):
        """The four rects around `r` that together cover the rest."""
        full = self.rect()
        return [
            QRect(full.left(), full.top(), full.width(), r.top()),
            QRect(full.left(), r.bottom() + 1, full.width(),
                  full.bottom() - r.bottom()),
            QRect(full.left(), r.top(), r.left(), r.height()),
            QRect(r.right() + 1, r.top(), full.right() - r.right(),
                  r.height()),
        ]

    def _selection_rect(self):
        """Current selection as a global-coordinate QRect, or None."""
        if self._origin is None or self._current is None:
            return None
        return QRect(self._origin, self._current).normalized()

    # -- interaction ----------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._origin = event.globalPos()
            self._current = event.globalPos()
            self.update()

    def mouseMoveEvent(self, event):
        if self._origin is not None:
            self._current = event.globalPos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._origin is not None:
            selection = self._selection_rect()
            self.close()
            if selection is not None:
                self.region_picked(selection)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            if self.cancelled:
                self.cancelled()
        else:
            super().keyPressEvent(event)


class RegionDisplayOverlay(QWidget):
    """Red overlay marking one saved restricted area on the desktop.

    The overlay itself is *click-through* (Qt.WindowTransparentForInput):
    mouse clicks land on whatever is underneath, so it never blocks the
    manager window or anything else.  Because a click-through window
    cannot host a clickable button, the X delete button is a separate
    tiny always-on-top window pinned to the region's top-right corner.
    """

    def __init__(self, index, rect, on_delete):
        super().__init__(None)
        self.index = index
        self.on_delete = on_delete  # callback(index)

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowTransparentForInput   # <- click-through
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setGeometry(rect)

        # Companion delete button: its own small window (NOT click-through)
        self.delete_btn = QPushButton("\u2715")
        self.delete_btn.setObjectName("roundNeutralBtn")
        self.delete_btn.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.delete_btn.setAttribute(Qt.WA_ShowWithoutActivating)
        self.delete_btn.setFixedSize(24, 24)
        self.delete_btn.setToolTip("Delete this restricted area")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.move(rect.x() + max(2, rect.width() - 28),
                             rect.y() + 4)
        self.delete_btn.clicked.connect(self._delete)

    def show(self):
        super().show()
        self.delete_btn.show()

    def closeEvent(self, event):
        self.delete_btn.close()
        super().closeEvent(event)

    def _delete(self):
        self.on_delete(self.index)

    def paintEvent(self, _event):
        painter = QPainter(self)
        # Light tint: this is only an indicator, not a wall
        painter.fillRect(self.rect(), QColor(233, 25, 22, 35))
        pen = QPen(QColor(theme.LIVE_RED), 2)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(
            self.rect().adjusted(8, 4, -8, -4),
            Qt.AlignLeft | Qt.AlignTop,
            f"Area {self.index + 1}  "
            f"({self.width()}x{self.height()})",
        )
