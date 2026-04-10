"""
Video trim dialog — drag the right handle to set the video out-point.

Styled after iOS Photos: the selected region is highlighted in amber,
the trimmed-off tail is darkened. Seeking the video to the handle
position lets the user see exactly what frame they're cutting at.
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
    QLabel,
    QVBoxLayout,
    QWidget,
)


class TrimTimeline(QWidget):
    """
    A horizontal scrubber with a single draggable right-edge handle.

    The amber region = kept video.  The dark region = trimmed off.
    """

    trim_changed = Signal(float)  # seconds

    _HANDLE_W = 14   # pixels wide
    _BAR_H_PAD = 10  # vertical padding inside the widget

    def __init__(self, duration: float, initial_trim: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._duration = max(duration, 0.001)
        self._trim = max(0.0, min(initial_trim, self._duration))
        self.setMinimumHeight(48)
        self.setMouseTracking(True)
        self.setCursor(Qt.SizeHorCursor)

    def trim(self) -> float:
        return self._trim

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)

        w, h = self.width(), self.height()
        bar_top = self._BAR_H_PAD
        bar_h = h - 2 * self._BAR_H_PAD
        handle_x = self._trim_to_x(self._trim)

        # Kept region — amber
        p.fillRect(QRect(0, bar_top, handle_x, bar_h), QColor(255, 190, 0))

        # Trimmed-off region — dark overlay
        p.fillRect(QRect(handle_x, bar_top, w - handle_x, bar_h), QColor(30, 30, 30, 200))

        # Handle — white vertical bar
        p.fillRect(QRect(handle_x - self._HANDLE_W // 2, 0, self._HANDLE_W, h), QColor(255, 255, 255))

        # Notch on the handle
        notch_w, notch_h = 3, 16
        notch_x = handle_x - notch_w // 2
        notch_y = (h - notch_h) // 2
        p.fillRect(QRect(notch_x, notch_y, notch_w, notch_h), QColor(160, 160, 160))

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self._update_trim(event.position().x())

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.buttons() & Qt.LeftButton:
            self._update_trim(event.position().x())

    def _update_trim(self, x: float) -> None:
        t = max(0.0, min(self._duration, x / max(self.width(), 1) * self._duration))
        if abs(t - self._trim) > 0.001:
            self._trim = t
            self.update()
            self.trim_changed.emit(t)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _trim_to_x(self, t: float) -> int:
        return int(t / self._duration * self.width())


class TrimDialog(QDialog):
    """
    Modal dialog for trimming the video out-point.

    Shows a video preview that seeks to the handle position as the user
    drags, so they can see the exact frame at the cut point.
    """

    def __init__(
        self,
        video_path: str,
        duration: float,
        default_trim: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Trim Video")
        self.setMinimumWidth(680)

        self._trim = max(0.0, min(default_trim, duration))

        # Video preview (audio muted — we're just picking a frame)
        self._video_widget = QVideoWidget()
        self._video_widget.setMinimumHeight(320)

        self._audio_out = QAudioOutput()
        self._audio_out.setVolume(0.0)

        self._player = QMediaPlayer(self)
        self._player.setVideoOutput(self._video_widget)
        self._player.setAudioOutput(self._audio_out)
        self._player.setSource(QUrl.fromLocalFile(str(Path(video_path).resolve())))
        # Seek to the default trim point once media is loaded
        self._player.mediaStatusChanged.connect(self._on_media_status)

        # Timeline handle
        self._timeline = TrimTimeline(duration, default_trim)
        self._timeline.trim_changed.connect(self._on_trim_changed)

        # Time readout
        self._time_label = QLabel(self._fmt(default_trim))
        self._time_label.setAlignment(Qt.AlignCenter)
        font = self._time_label.font()
        font.setPointSize(13)
        self._time_label.setFont(font)

        # OK / Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self._video_widget, stretch=1)
        layout.addSpacing(4)
        layout.addWidget(self._timeline)
        layout.addWidget(self._time_label)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def trim_seconds(self) -> float:
        return self._trim

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_trim_changed(self, t: float) -> None:
        self._trim = t
        self._time_label.setText(self._fmt(t))
        self._player.setPosition(int(t * 1000))
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.LoadedMedia:
            self._player.setPosition(int(self._trim * 1000))
            self._player.pause()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt(seconds: float) -> str:
        m = int(seconds) // 60
        s = seconds - m * 60
        return f"{m:02d}:{s:05.2f}"
