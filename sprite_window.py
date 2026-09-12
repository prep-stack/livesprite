#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sprite window.

A frameless, transparent, always-on-top window that plays one GIF at a
time and walks around the desktop:

  * weighted random animation switching at the end of each GIF loop
  * movement based on the current animation's direction/pixels
  * edge behavior (wrap / bounce / stop) over all allowed screens
  * restricted screens are skipped: the sprite jumps over them to the
    next allowed screen in its direction of travel
  * drag with the left mouse button; a plain click opens the stream page
    when the streamer is live
  * when the tracked channel goes live the sprite switches to its live
    animation and stays there until clicked (visited)
"""

import logging
import random
import sys
import webbrowser

from PyQt5.QtCore import QBuffer, QByteArray, QPoint, QRect, Qt, QTimer
from PyQt5.QtGui import QGuiApplication, QMovie
from PyQt5.QtWidgets import QLabel, QMenu, QWidget

from config import ANIMATION_SWITCH_CHANCE, MOVEMENT_INTERVAL_MS

logger = logging.getLogger(__name__)

CLICK_DRAG_THRESHOLD = 6  # pixels of movement that still counts as a click
TOPMOST_INTERVAL_MS = 5000  # how often the on-top flag is re-asserted

# Win32 z-order plumbing.  IMPORTANT: SetWindowPos must be declared with
# proper argument types - with plain ints, the special handles -1/-2
# (HWND_TOPMOST/HWND_NOTOPMOST) get truncated on 64-bit Python and the
# call fails silently (returns 0).  This exact bug made the old 30s
# re-assert a no-op.
_HWND_TOPMOST = -1
_HWND_NOTOPMOST = -2
_SWP_FLAGS = 0x0002 | 0x0001 | 0x0010  # NOMOVE | NOSIZE | NOACTIVATE
_set_window_pos = None
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    _set_window_pos = ctypes.WinDLL(
        "user32", use_last_error=True
    ).SetWindowPos
    _set_window_pos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    _set_window_pos.restype = wintypes.BOOL


def _set_zorder(hwnd, insert_after):
    """SetWindowPos wrapper; returns True on success."""
    if _set_window_pos is None:
        return False
    return bool(_set_window_pos(hwnd, insert_after, 0, 0, 0, 0, _SWP_FLAGS))


class SpriteWindow(QWidget):
    """Transparent desktop window showing one walking sprite."""

    def __init__(self, model, stream_service, on_closed=None, on_moved=None):
        super().__init__(None)
        self.model = model
        self.streams = stream_service
        self.on_closed = on_closed    # callback(asset_dir, deliberate)
        self.on_moved = on_moved      # callback(asset_dir, x, y)
        # True only when the user explicitly removed this sprite.  An OS
        # shutdown or app quit also closes the window, but then the sprite
        # must stay in the session so it respawns on the next start.
        self.deliberate_close = False

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle(f"Sprite: {model.asset_dir}")

        self.label = QLabel(self)
        self.label.setAttribute(Qt.WA_TranslucentBackground)

        # Animation state
        self.movie = None
        self.current_animation = None
        self._dx = 0
        self._dy = 0
        self._saw_frame = False   # used to detect the end of a GIF loop

        # Drag state
        self._dragging = False
        self._drag_offset = QPoint()
        self._press_pos = QPoint()

        # Track the sprite's channel so the poller checks it
        chan = self.model.stream_channel()
        if chan:
            self.streams.track(
                *chan, youtube_method=self.model.youtube_check_method
            )
            self.streams.status_changed.connect(self._on_stream_status)

        # Movement loop
        self.movement_timer = QTimer(self)
        self.movement_timer.timeout.connect(self._step)
        self.movement_timer.start(MOVEMENT_INTERVAL_MS)

        # Keep the sprite above other windows.  Windows demotes topmost
        # windows (fullscreen video, Discord overlay, Explorer restarts)
        # and other topmost windows can insert above us *within* the
        # topmost layer - re-assert frequently; two Win32 calls every few
        # seconds cost nothing and recovery is near-instant.
        self.topmost_timer = QTimer(self)
        self.topmost_timer.timeout.connect(self.assert_topmost)
        if self.model.always_on_top:
            self.topmost_timer.start(TOPMOST_INTERVAL_MS)

        self.select_random_animation()

    def assert_topmost(self):
        """Force the sprite back to the TOP of the topmost layer.

        Re-applying HWND_TOPMOST alone is a no-op when the window is
        already topmost - but other topmost windows (Discord overlay,
        fullscreen browser video) can still sit ABOVE us within the
        topmost layer.  Dropping to NOTOPMOST and immediately going back
        to TOPMOST forces Windows to re-insert the sprite at the top of
        that layer.  SWP_NOACTIVATE keeps focus untouched; only z-order
        changes, so there is no flicker.
        """
        if not self.isVisible() or not self.model.always_on_top:
            return
        try:
            hwnd = int(self.winId())
            ok1 = _set_zorder(hwnd, _HWND_NOTOPMOST)
            ok2 = _set_zorder(hwnd, _HWND_TOPMOST)
            if not (ok1 and ok2):
                logger.debug("assert_topmost SetWindowPos returned false")
        except Exception as e:  # non-Windows or unexpected failure
            logger.debug("assert_topmost failed: %s", e)

    def set_always_on_top(self, enabled):
        """Toggle keep-on-top at runtime and persist the choice."""
        self.model.always_on_top = enabled
        self.model.save()
        if enabled:
            self.assert_topmost()
            self.topmost_timer.start(TOPMOST_INTERVAL_MS)
        else:
            self.topmost_timer.stop()
            try:
                _set_zorder(int(self.winId()), _HWND_NOTOPMOST)
            except Exception as e:
                logger.debug("clearing topmost failed: %s", e)
        logger.info("%s: keep on top %s", self.model.asset_dir,
                    "enabled" if enabled else "disabled")

    def showEvent(self, event):
        super().showEvent(event)
        # Re-assert topmost whenever the sprite (re)appears
        QTimer.singleShot(0, self.assert_topmost)

    # -- animation ------------------------------------------------------
    def select_random_animation(self):
        """Pick the next animation.  Live animation wins when applicable."""
        # If live and not yet visited, force the live animation
        if self._should_show_live():
            self.set_animation(self.model.live_animation)
            chan = self.model.stream_channel()
            if chan and not self.streams.is_notified(*chan):
                self.streams.mark_notified(*chan)
                logger.info("%s: %s is LIVE - showing live animation",
                            self.model.asset_dir, chan[1])
            return

        # Weighted random choice among normal animations
        candidates = [
            a for name, a in self.model.animations.items()
            if name != self.model.live_animation and a.chance > 0
        ]
        if not candidates:  # everything is 0% or only a live animation exists
            candidates = list(self.model.animations.values())
        weights = [max(a.chance, 1) for a in candidates]
        choice = random.choices(candidates, weights=weights, k=1)[0]
        self.set_animation(choice.filename)

    def set_animation(self, name):
        """Load and start playing the given GIF."""
        anim = self.model.animations.get(name)
        if anim is None:
            return
        if self.movie is not None:
            self.movie.stop()
            self.movie.deleteLater()

        self.current_animation = name
        self._dx, self._dy = anim.delta()
        self._saw_frame = False

        # Load the GIF through a memory buffer instead of QMovie(path):
        # QMovie keeps a file handle open for as long as it plays, which
        # locks the GIF on Windows and makes pack updates fail while the
        # sprite is active.  With the bytes in memory the file on disk
        # stays free to overwrite/delete at any time.
        path = self.model.animation_path(name)
        try:
            with open(path, "rb") as f:
                self._gif_data = QByteArray(f.read())
        except OSError as e:
            logger.error("Cannot read GIF %s: %s", path, e)
            return
        self._gif_buffer = QBuffer(self._gif_data)
        self._gif_buffer.open(QBuffer.ReadOnly)
        self.movie = QMovie()
        self.movie.setDevice(self._gif_buffer)
        self.movie.setFormat(b"gif")
        if not self.movie.isValid():
            logger.error("Invalid GIF: %s", path)
            return
        # Playback speed as a percentage (100 = the GIF's own timing)
        self.movie.setSpeed(max(10, min(500, anim.speed)))
        self.movie.frameChanged.connect(self._on_frame_changed)
        self.label.setMovie(self.movie)
        self.movie.start()

        size = self.movie.currentPixmap().size()
        if size.isValid() and not size.isEmpty():
            self.resize(size)
            self.label.resize(size)

    def _on_frame_changed(self, frame_number):
        """Detect the end of a GIF loop and maybe switch animation."""
        if frame_number == 0 and self._saw_frame:
            if self._should_show_live():
                if self.current_animation != self.model.live_animation:
                    self.select_random_animation()
            elif self.current_animation == self.model.live_animation:
                # Live ended or was visited - go back to normal behavior
                self.select_random_animation()
            elif random.random() < ANIMATION_SWITCH_CHANCE:
                self.select_random_animation()
        self._saw_frame = True

    # -- live stream handling ----------------------------------------------
    def _should_show_live(self):
        """True when the channel is live and the user hasn't clicked yet."""
        if not self.model.live_animation:
            return False
        chan = self.model.stream_channel()
        if not chan:
            return False
        return (self.streams.is_live(*chan)
                and not self.streams.is_visited(*chan))

    def _on_stream_status(self, platform, channel, is_live):
        """React immediately when the tracked channel changes status."""
        chan = self.model.stream_channel()
        if not chan or (platform, channel) != (chan[0], chan[1].lower()):
            return
        if is_live and self._should_show_live():
            self.set_animation(self.model.live_animation)
            self.streams.mark_notified(platform, channel)
            logger.info("%s: %s went LIVE", self.model.asset_dir, channel)
            # A live notification must be seen - jump back on top now
            self.assert_topmost()
        elif (not is_live
              and self.current_animation == self.model.live_animation):
            self.select_random_animation()
        self.apply_visibility()

    def apply_visibility(self):
        """Show/hide the sprite according to its hide settings.

        - hide_when_offline: visible only while the channel is live
        - hide_when_notified (in addition): also hidden after the user
          double-clicked the live notification (visited), until the
          channel goes offline and comes back live again
        """
        if not self.model.hide_when_offline:
            return  # always visible - never touch visibility here
        chan = self.model.stream_channel()
        if not chan:
            return
        is_live = self.streams.is_live(*chan)
        visible = is_live
        if visible and self.model.hide_when_notified:
            if self.streams.is_visited(*chan):
                visible = False
        self.setVisible(visible)

    # -- movement ---------------------------------------------------------
    def _step(self):
        """One movement step: advance, then handle edges and restrictions."""
        if self._dragging or (self._dx == 0 and self._dy == 0):
            return
        if not self.isVisible():
            return

        new_x = self.x() + self._dx
        new_y = self.y() + self._dy

        new_x, new_y = self._apply_edge_behavior(new_x, new_y)

        # Skip over restricted screens in the direction of travel
        if self._is_restricted_at(new_x, new_y):
            dest = self._skip_destination(new_x, new_y)
            if dest is not None:
                new_x, new_y = dest
            else:
                return  # nowhere to go this step

        self.move(new_x, new_y)

    def _allowed_geometry(self):
        """Bounding rect of all screens the sprite may use."""
        screens = QGuiApplication.screens()
        if not self.model.allow_multi_screen:
            return QGuiApplication.primaryScreen().availableGeometry()
        rects = [
            s.geometry() for i, s in enumerate(screens)
            if i not in self.model.restricted_screens
        ]
        if not rects:
            return QGuiApplication.primaryScreen().availableGeometry()
        combined = rects[0]
        for r in rects[1:]:
            combined = combined.united(r)
        return combined

    def _apply_edge_behavior(self, new_x, new_y):
        """Wrap/bounce/stop at the outer boundary of the allowed area."""
        area = self._allowed_geometry()
        behavior = self.model.edge_behavior

        out_left = new_x < area.left()
        out_right = new_x + self.width() > area.right()
        out_top = new_y < area.top()
        out_bottom = new_y + self.height() > area.bottom()
        if not (out_left or out_right or out_top or out_bottom):
            return new_x, new_y

        if behavior == "wrap":
            if out_left:
                new_x = area.right() - self.width()
            elif out_right:
                new_x = area.left()
            if out_top:
                new_y = area.bottom() - self.height()
            elif out_bottom:
                new_y = area.top()
        elif behavior == "bounce":
            if out_left or out_right:
                self._dx = -self._dx
                new_x = area.left() if out_left else area.right() - self.width()
            if out_top or out_bottom:
                self._dy = -self._dy
                new_y = area.top() if out_top else area.bottom() - self.height()
        else:  # stop
            new_x = max(area.left(), min(new_x, area.right() - self.width()))
            new_y = max(area.top(), min(new_y, area.bottom() - self.height()))
            self._dx = self._dy = 0
        return new_x, new_y

    # -- restricted screens -------------------------------------------------
    def _is_restricted_at(self, x, y):
        """True when >30% of the sprite would sit on a restricted screen."""
        if not self.model.restricted_screens:
            return False
        rect = QRect(x, y, self.width(), self.height())
        area = rect.width() * rect.height()
        if area <= 0:
            return False
        for i, screen in enumerate(QGuiApplication.screens()):
            if i in self.model.restricted_screens:
                inter = rect.intersected(screen.geometry())
                if inter.isValid():
                    if inter.width() * inter.height() > area * 0.3:
                        return True
        return False

    def _skip_destination(self, new_x, new_y):
        """Jump over a restricted screen to the next allowed screen.

        Picks the next allowed screen in the primary direction of travel;
        wraps to the far side when there is none.
        """
        screens = QGuiApplication.screens()
        allowed = [
            s.geometry() for i, s in enumerate(screens)
            if i not in self.model.restricted_screens
        ]
        if not allowed:
            return None

        cx = new_x + self.width() // 2
        cy = new_y + self.height() // 2

        if abs(self._dx) >= abs(self._dy) and self._dx != 0:
            if self._dx > 0:  # moving right
                cand = [g for g in allowed if g.left() > cx]
                target = (min(cand, key=lambda g: g.left()) if cand
                          else min(allowed, key=lambda g: g.left()))
                dest_x = target.left()
            else:             # moving left
                cand = [g for g in allowed if g.right() < cx]
                target = (max(cand, key=lambda g: g.right()) if cand
                          else max(allowed, key=lambda g: g.right()))
                dest_x = target.right() - self.width()
            dest_y = max(target.top(),
                         min(new_y, target.bottom() - self.height()))
            return dest_x, dest_y

        if self._dy != 0:
            if self._dy > 0:  # moving down
                cand = [g for g in allowed if g.top() > cy]
                target = (min(cand, key=lambda g: g.top()) if cand
                          else min(allowed, key=lambda g: g.top()))
                dest_y = target.top()
            else:             # moving up
                cand = [g for g in allowed if g.bottom() < cy]
                target = (max(cand, key=lambda g: g.bottom()) if cand
                          else max(allowed, key=lambda g: g.bottom()))
                dest_y = target.bottom() - self.height()
            dest_x = max(target.left(),
                         min(new_x, target.right() - self.width()))
            return dest_x, dest_y
        return None

    def ensure_on_allowed_screen(self):
        """Move the sprite onto an allowed screen if needed.

        Keeps the vertical (y) position as close as possible to where the
        sprite was - only the x position is shifted onto the nearest
        allowed screen.  This matters for sprites that only walk left and
        right: their height on the screen should never be reset.
        """
        if not self._is_restricted_at(self.x(), self.y()):
            return
        screens = QGuiApplication.screens()
        allowed = [
            s.geometry() for i, s in enumerate(screens)
            if i not in self.model.restricted_screens
        ]
        if not allowed:
            return
        # Pick the allowed screen whose center is closest horizontally
        cx = self.x() + self.width() // 2
        target = min(allowed, key=lambda g: abs(g.center().x() - cx))
        # Clamp x into the target screen; keep y, clamped into the screen
        new_x = max(target.left(),
                    min(self.x(), target.right() - self.width()))
        new_y = max(target.top(),
                    min(self.y(), target.bottom() - self.height()))
        self.move(new_x, new_y)

    # -- mouse interaction ----------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._press_pos = event.globalPos()
            self._drag_offset = event.globalPos() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPos() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            moved = (event.globalPos() - self._press_pos).manhattanLength()
            if moved > CLICK_DRAG_THRESHOLD:
                # This was a drag - remember the new spot
                self.ensure_on_allowed_screen()
                if self.on_moved:
                    self.on_moved(self.model.asset_dir, self.x(), self.y())
                # The user is interacting with the sprite - make sure it
                # is right at the top again
                self.assert_topmost()
            # A single click does nothing; double-click opens the stream
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._handle_click()
            event.accept()

    def _handle_click(self):
        """Open the stream page and mark the channel visited when live."""
        chan = self.model.stream_channel()
        url = self.model.stream_url()
        if not chan or not url:
            return
        if self.streams.is_live(*chan):
            self.streams.mark_visited(*chan)
            logger.info("%s: opened live stream %s", self.model.asset_dir, url)
            # Leave the live animation now that the user has seen it
            if self.current_animation == self.model.live_animation:
                self.select_random_animation()
            # With hide-when-notified the sprite goes away again until
            # the next stream
            self.apply_visibility()
        webbrowser.open(url)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        chan = self.model.stream_channel()
        if chan:
            live = self.streams.is_live(*chan)
            status = menu.addAction(
                f"{chan[1]} ({chan[0]}): {'LIVE' if live else 'offline'}"
            )
            status.setEnabled(False)
            menu.addSeparator()
        open_action = menu.addAction("Open stream page")
        top_action = menu.addAction("Keep on top")
        top_action.setCheckable(True)
        top_action.setChecked(self.model.always_on_top)
        close_action = menu.addAction("Close sprite")
        chosen = menu.exec_(event.globalPos())
        if chosen == open_action:
            self._handle_click()
        elif chosen == top_action:
            self.set_always_on_top(top_action.isChecked())
        elif chosen == close_action:
            self.request_close()

    # -- cleanup ---------------------------------------------------------
    def request_close(self):
        """Close because the user explicitly removed this sprite."""
        self.deliberate_close = True
        self.close()

    def closeEvent(self, event):
        self.movement_timer.stop()
        if self.movie is not None:
            self.movie.stop()
        chan = self.model.stream_channel()
        if chan:
            try:
                self.streams.status_changed.disconnect(self._on_stream_status)
            except TypeError:
                pass
            self.streams.untrack(*chan)
        if self.on_closed:
            self.on_closed(self.model.asset_dir, self.deliberate_close)
        event.accept()
