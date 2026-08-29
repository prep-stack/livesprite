#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Modern dark theme for LiveSprite (v2.1.0).

Pure cosmetics: one global Qt Style Sheet applied to the QApplication,
plus a helper that switches the native Windows title bar to dark mode.
Removing `theme.apply(app)` from main.py restores the old look - no
program logic lives in this file.

Palette (matches the design concept):
  window     #15161e   deep navy background
  card       #1e1f2b   panels / lists / menus
  input      #12131a   text fields, spinboxes, tables
  border     #32344a   subtle outlines
  accent     #7c5cff   purple (primary buttons, focus, selection)
  text       #e6e6f0   main text
  muted      #8b8fa3   secondary text / hints
  live red   #e91916   LIVE markers (set inline where used)
"""

import sys

WINDOW_BG = "#15161e"
CARD_BG = "#1e1f2b"
INPUT_BG = "#12131a"
BORDER = "#32344a"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#8d71ff"
ACCENT_PRESSED = "#6b4de6"
TEXT = "#e6e6f0"
MUTED = "#8b8fa3"
LIVE_RED = "#e91916"

STYLESHEET = """
/* -- base ------------------------------------------------------------- */
QWidget {
    color: #e6e6f0;
    font-size: 10pt;
}
QMainWindow, QDialog, QMessageBox {
    background-color: #15161e;
}
QLabel {
    background: transparent;
}
QToolTip {
    background-color: #1e1f2b;
    color: #e6e6f0;
    border: 1px solid #32344a;
    padding: 4px 8px;
}

/* -- buttons ---------------------------------------------------------- */
QPushButton {
    background-color: #262838;
    color: #e6e6f0;
    border: 1px solid #32344a;
    border-radius: 8px;
    padding: 6px 14px;
}
QPushButton:hover { background-color: #2e3046; }
QPushButton:pressed { background-color: #212233; }
QPushButton:disabled { color: #6a6d85; background-color: #1c1d29; }

QPushButton[accent="true"] {
    background-color: #7c5cff;
    color: #ffffff;
    border: none;
    font-weight: bold;
}
QPushButton[accent="true"]:hover { background-color: #8d71ff; }
QPushButton[accent="true"]:pressed { background-color: #6b4de6; }
QPushButton[accent="true"]:disabled {
    background-color: #453a75; color: #a9a4c9;
}

QPushButton[link="true"] {
    background-color: transparent;
    color: #9d86ff;
    border: 1px solid #3d3564;
}
QPushButton[link="true"]:hover {
    background-color: #221f33; color: #b7a6ff;
}

QPushButton#roundAccentBtn {
    background-color: #7c5cff;
    color: #ffffff;
    border: none;
    border-radius: 13px;
    padding: 0;
    font-weight: bold;
    font-size: 13pt;
}
QPushButton#roundAccentBtn:hover { background-color: #8d71ff; }
QPushButton#roundNeutralBtn {
    background-color: #262838;
    border: 1px solid #32344a;
    border-radius: 13px;
    padding: 0;
}
QPushButton#roundNeutralBtn:hover { background-color: #2e3046; }

/* -- lists (the two sprite panels) ------------------------------------ */
QListWidget {
    background-color: #1e1f2b;
    border: 1px solid #262838;
    border-radius: 10px;
    padding: 4px;
    outline: none;
}
QListWidget::item {
    border-bottom: 1px solid #262838;
    border-radius: 6px;
    padding: 2px;
}
QListWidget::item:hover { background-color: #26283a; }
QListWidget::item:selected {
    background-color: #2b2d43;
    border: 1px solid #7c5cff;
}

/* -- group boxes (settings sections) ----------------------------------- */
QGroupBox {
    background-color: #1e1f2b;
    border: 1px solid #262838;
    border-radius: 10px;
    margin-top: 12px;
    padding: 10px 6px 6px 6px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #e6e6f0;
}

/* -- inputs ------------------------------------------------------------ */
QLineEdit, QSpinBox, QComboBox {
    background-color: #12131a;
    color: #e6e6f0;
    border: 1px solid #32344a;
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: #7c5cff;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border: 1px solid #7c5cff;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
    color: #6a6d85; background-color: #191a23;
}
QSpinBox::up-button, QSpinBox::down-button {
    background-color: #262838;
    border: none;
    width: 16px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background-color: #7c5cff;
}
QSpinBox::up-arrow { image: url(%ARROW_UP%); width: 8px; height: 5px; }
QSpinBox::down-arrow { image: url(%ARROW_DOWN%); width: 8px; height: 5px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow {
    image: url(%ARROW_DOWN%);
    width: 10px;
    height: 6px;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background-color: #1e1f2b;
    color: #e6e6f0;
    border: 1px solid #32344a;
    selection-background-color: #7c5cff;
    selection-color: #ffffff;
    outline: none;
}

/* -- checkboxes -------------------------------------------------------- */
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox:disabled { color: #6a6d85; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #32344a;
    border-radius: 4px;
    background-color: #12131a;
}
QCheckBox::indicator:hover { border-color: #7c5cff; }
QCheckBox::indicator:checked {
    background-color: #7c5cff;
    border-color: #7c5cff;
    image: url(%CHECKMARK%);
}
QCheckBox::indicator:checked:disabled { background-color: #453a75; }

/* -- table (animations) ------------------------------------------------ */
QTableWidget {
    background-color: #12131a;
    border: 1px solid #262838;
    border-radius: 8px;
    gridline-color: #262838;
    outline: none;
}
QTableWidget::item:selected { background-color: #2b2d43; }
QHeaderView::section {
    background-color: #1e1f2b;
    color: #8b8fa3;
    border: none;
    border-bottom: 1px solid #32344a;
    border-right: 1px solid #262838;
    padding: 4px 6px;
}
QTableCornerButton::section {
    background-color: #1e1f2b;
    border: none;
    border-bottom: 1px solid #32344a;
}

/* -- menus (tray + popups) ---------------------------------------------- */
QMenu {
    background-color: #1e1f2b;
    color: #e6e6f0;
    border: 1px solid #32344a;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item { padding: 6px 24px 6px 12px; border-radius: 5px; }
QMenu::item:selected { background-color: #7c5cff; color: #ffffff; }
QMenu::separator { height: 1px; background: #32344a; margin: 4px 8px; }
QMenu::indicator { width: 14px; height: 14px; }

/* -- scrollbars ---------------------------------------------------------- */
QScrollBar:vertical {
    background: transparent; width: 10px; margin: 2px;
}
QScrollBar::handle:vertical {
    background: #32344a; border-radius: 4px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #7c5cff; }
QScrollBar:horizontal {
    background: transparent; height: 10px; margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #32344a; border-radius: 4px; min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #7c5cff; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


def _make_arrow_icons():
    """Render tiny up/down arrow PNGs for spinboxes and combo boxes.

    QSS cannot draw triangles, so we paint two small pixmaps into the
    temp folder once per run and reference them from the stylesheet.
    Returns (up_path, down_path) with forward slashes for QSS url().
    """
    import os
    import tempfile
    from PyQt5.QtCore import QPointF, Qt
    from PyQt5.QtGui import QColor, QPainter, QPixmap, QPolygonF

    out = {}
    for name, points in (
        ("up", [(1, 9), (11, 9), (6, 3)]),
        ("down", [(1, 3), (11, 3), (6, 9)]),
    ):
        pixmap = QPixmap(12, 12)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(MUTED))
        painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))
        painter.end()
        path = os.path.join(
            tempfile.gettempdir(), f"livesprite_arrow_{name}.png"
        )
        pixmap.save(path, "PNG")
        out[name] = path.replace("\\", "/")

    # White checkmark for checked checkboxes
    from PyQt5.QtGui import QPen
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor("#ffffff"))
    pen.setWidthF(2.0)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawLine(QPointF(2.5, 6.5), QPointF(5, 9))
    painter.drawLine(QPointF(5, 9), QPointF(9.5, 3.5))
    painter.end()
    path = os.path.join(tempfile.gettempdir(), "livesprite_check.png")
    pixmap.save(path, "PNG")
    out["check"] = path.replace("\\", "/")
    return out["up"], out["down"], out["check"]


def apply(app):
    """Apply the dark theme to the whole application (one call)."""
    from PyQt5.QtGui import QColor, QPalette
    stylesheet = STYLESHEET
    try:
        up, down, check = _make_arrow_icons()
        stylesheet = stylesheet.replace("%ARROW_UP%", up)
        stylesheet = stylesheet.replace("%ARROW_DOWN%", down)
        stylesheet = stylesheet.replace("%CHECKMARK%", check)
    except Exception:  # icons are optional decoration
        stylesheet = stylesheet.replace("url(%ARROW_UP%)", "none")
        stylesheet = stylesheet.replace("url(%ARROW_DOWN%)", "none")
        stylesheet = stylesheet.replace("url(%CHECKMARK%)", "none")
    app.setStyleSheet(stylesheet)
    # Placeholder text color cannot be set from QSS - use the palette.
    palette = app.palette()
    palette.setColor(QPalette.PlaceholderText, QColor(MUTED))
    app.setPalette(palette)


def dark_title_bar(window):
    """Turn the native Windows title bar dark for `window`.

    Uses DwmSetWindowAttribute(DWMWA_USE_IMMERSIVE_DARK_MODE); silently
    does nothing on failure or on non-Windows platforms, so this can
    never break the app.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = int(window.winId())
        value = ctypes.c_int(1)
        for attribute in (20, 19):  # 20 = Win10 20H1+, 19 = older builds
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
            if result == 0:
                break
    except Exception:  # pragma: no cover - purely cosmetic
        pass
