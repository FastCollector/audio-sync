"""
Video trim dialog — drag left/right handles to set in-point and out-point.

Styled after iOS Photos: amber region = kept, dark regions = trimmed off.
Video preview seeks to whichever handle was last moved.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRect, QUrl, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

_HANDLE_W = 14
_BAR_H_PAD = 8
_SNAP_PX = _HANDLE_W  # pixel radius within which a click snaps to a handle


class TrimTimeline(QWidget):
    """
    Horizontal timeline with draggable left (in) and right (out) handles.

    Signals:
        range_changed(start_seconds, end_seconds)
        active_handle_changed(seconds)  — which handle is being moved (for video seek)
    """

    range_changed = Signal(float, float)
    active_handle_changed = Signal(float)

    def __init__(
        self,
        duration: float,
        initial_start: float,
        initial_end: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._duration = max(duration, 0.001)
        self._start = max(0.0, min(initial_start, self._duration))
        self._end = max(self._start, min(initial_end, self._duration))
        self._dragging: str | None = None  # "start" | "end" | None
        self.setMinimumHeight(48)
        self.setMouseTracking(True)

    def start(self) -> float:
        return self._start

    def end(self) -> float:
        return self._end

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)

        w, h = self.width(), self.height()
        bar_top = _BAR_H_PAD
        bar_h = h - 2 * _BAR_H_PAD

        sx = self._t_to_x(self._start)
        ex = self._t_to_x(self._end)

        # Trimmed-off regions — dark
        p.fillRect(QRect(0, bar_top, sx, bar_h), QColor(30, 30, 30, 200))
        p.fillRect(QRect(ex, bar_top, w - ex, bar_h), QColor(30, 30, 30, 200))

        # Kept region — amber
        p.fillRect(QRect(sx, bar_top, ex - sx, bar_h), QColor(255, 190, 0))

        # Draw both handles
        for x in (sx, ex):
            p.fillRect(QRect(x - _HANDLE_W // 2, 0, _HANDLE_W, h), QColor(255, 255, 255))
            notch_w, notch_h = 3, 16
            p.fillRect(
                QRect(x - notch_w // 2, (h - notch_h) // 2, notch_w, notch_h),
                QColor(160, 160, 160),
            )

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.LeftButton:
            return
        x = event.position().x()
        sx = self._t_to_x(self._start)
        ex = self._t_to_x(self._end)
        # Snap to nearest handle if within snap radius
        if abs(x - sx) <= _SNAP_PX and abs(x - sx) <= abs(x - ex):
            self._dragging = "start"
        elif abs(x - ex) <= _SNAP_PX:
            self._dragging = "end"
        else:
            # Click in the middle — move nearest handle
            self._dragging = "start" if abs(x - sx) < abs(x - ex) else "end"
        self._update(x)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.buttons() & Qt.LeftButton and self._dragging:
            self._update(event.position().x())
            self.setCursor(Qt.SizeHorCursor)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._dragging = None

    def _update(self, x: float) -> None:
        t = max(0.0, min(self._duration, x / max(self.width(), 1) * self._duration))
        if self._dragging == "start":
            self._start = min(t, self._end - 0.1)
            self.active_handle_changed.emit(self._start)
        else:
            self._end = max(t, self._start + 0.1)
            self.active_handle_changed.emit(self._end)
        self.update()
        self.range_changed.emit(self._start, self._end)

    # ------------------------------------------------------------------

    def _t_to_x(self, t: float) -> int:
        return int(t / self._duration * self.width())


class TrimDialog(QDialog):
    """Modal dialog for trimming video in/out points."""

    def __init__(
        self,
        video_path: str,
        duration: float,
        default_start: float,
        default_end: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Trim Video")
        self.setMinimumWidth(680)

        self._start = max(0.0, min(default_start, duration))
        self._end = max(self._start, min(default_end, duration))

        # Video preview (muted)
        self._video_widget = QVideoWidget()
        self._video_widget.setMinimumHeight(300)

        self._audio_out = QAudioOutput()
        self._audio_out.setVolume(0.0)

        self._player = QMediaPlayer(self)
        self._player.setVideoOutput(self._video_widget)
        self._player.setAudioOutput(self._audio_out)
        self._player.setSource(QUrl.fromLocalFile(str(Path(video_path).resolve())))
        self._player.mediaStatusChanged.connect(self._on_media_status)

        # Timeline with two handles
        self._timeline = TrimTimeline(duration, self._start, self._end)
        self._timeline.range_changed.connect(self._on_range_changed)
        self._timeline.active_handle_changed.connect(self._on_handle_moved)

        # Time labels: start / end
        self._start_label = QLabel(self._fmt(self._start))
        self._start_label.setAlignment(Qt.AlignLeft)
        self._end_label = QLabel(self._fmt(self._end))
        self._end_label.setAlignment(Qt.AlignRight)
        for lbl in (self._start_label, self._end_label):
            font = lbl.font()
            font.setPointSize(12)
            lbl.setFont(font)

        time_row = QHBoxLayout()
        time_row.addWidget(self._start_label)
        time_row.addStretch()
        time_row.addWidget(self._end_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self._video_widget, stretch=1)
        layout.addSpacing(4)
        layout.addWidget(self._timeline)
        layout.addLayout(time_row)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def start_seconds(self) -> float:
        return self._start

    def end_seconds(self) -> float:
        return self._end

    # ------------------------------------------------------------------

    def _on_range_changed(self, start: float, end: float) -> None:
        self._start = start
        self._end = end
        self._start_label.setText(self._fmt(start))
        self._end_label.setText(self._fmt(end))

    def _on_handle_moved(self, t: float) -> None:
        self._player.setPosition(int(t * 1000))
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.LoadedMedia:
            self._player.setPosition(int(self._end * 1000))
            self._player.pause()

    @staticmethod
    def _fmt(seconds: float) -> str:
        m = int(seconds) // 60
        s = seconds - m * 60
        return f"{m:02d}:{s:05.2f}"
