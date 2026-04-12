"""
Video trim dialog — drag left/right handles to set in-point and out-point.
"""

from __future__ import annotations

import queue
import subprocess
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.ffmpeg_utils import get_ffmpeg_executable

_HANDLE_W = 14
_BAR_H_PAD = 8
_SNAP_PX = _HANDLE_W
_PREVIEW_H = 300


def _extract_frame(video_path: str, t: float) -> str:
    try:
        ffmpeg = get_ffmpeg_executable()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        subprocess.run(
            [ffmpeg, "-y", "-ss", f"{t:.3f}", "-i", video_path,
             "-frames:v", "1", "-q:v", "3", tmp],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
        )
        return tmp
    except Exception:
        return ""


class TrimTimeline(QWidget):
    range_changed = Signal(float, float)
    handle_moved = Signal(float)
    handle_released = Signal(float)
    playhead_scrubbed = Signal(float)

    def __init__(self, duration: float, initial_start: float, initial_end: float,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._duration = max(duration, 0.001)
        self._start = max(0.0, min(initial_start, self._duration))
        self._end = max(self._start, min(initial_end, self._duration))
        self._playhead = self._start
        self._dragging: str | None = None
        self._last_t: float = initial_end
        self.setMinimumHeight(48)
        self.setMouseTracking(True)

    def start(self) -> float:
        return self._start

    def end(self) -> float:
        return self._end

    def set_playhead(self, t: float) -> None:
        clamped = max(self._start, min(self._end, t))
        if abs(clamped - self._playhead) < 0.001:
            return
        self._playhead = clamped
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        w, h = self.width(), self.height()
        bar_top, bar_h = _BAR_H_PAD, h - 2 * _BAR_H_PAD
        sx, ex = self._t_to_x(self._start), self._t_to_x(self._end)
        px = self._t_to_x(self._playhead)
        p.fillRect(QRect(0, bar_top, sx, bar_h), QColor(30, 30, 30, 200))
        p.fillRect(QRect(ex, bar_top, w - ex, bar_h), QColor(30, 30, 30, 200))
        p.fillRect(QRect(sx, bar_top, ex - sx, bar_h), QColor(255, 190, 0))
        for x in (sx, ex):
            p.fillRect(QRect(x - _HANDLE_W // 2, 0, _HANDLE_W, h), QColor(255, 255, 255))
            p.fillRect(QRect(x - 1, (h - 16) // 2, 3, 16), QColor(160, 160, 160))
        p.fillRect(QRect(px - 1, 0, 3, h), QColor(255, 64, 64))

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.LeftButton:
            return
        x = event.position().x()
        sx, ex = self._t_to_x(self._start), self._t_to_x(self._end)
        if abs(x - sx) <= _SNAP_PX and abs(x - sx) <= abs(x - ex):
            self._dragging = "start"
        elif abs(x - ex) <= _SNAP_PX:
            self._dragging = "end"
        else:
            self._dragging = "playhead"
        self._update(x)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.buttons() & Qt.LeftButton and self._dragging:
            self._update(event.position().x())
            self.setCursor(Qt.SizeHorCursor)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self._dragging in ("start", "end"):
            self.handle_released.emit(self._last_t)
        self._dragging = None

    def _update(self, x: float) -> None:
        t = max(0.0, min(self._duration, x / max(self.width(), 1) * self._duration))
        if self._dragging == "start":
            self._start = min(t, self._end - 0.1)
            self._last_t = self._start
        elif self._dragging == "end":
            self._end = max(t, self._start + 0.1)
            self._last_t = self._end
        else:
            self._playhead = max(self._start, min(self._end, t))
            self.playhead_scrubbed.emit(self._playhead)
            self.update()
            return
        self._playhead = max(self._start, min(self._end, self._playhead))
        self.update()
        self.range_changed.emit(self._start, self._end)
        self.handle_moved.emit(self._last_t)

    def _t_to_x(self, t: float) -> int:
        return int(t / self._duration * self.width())


class TrimDialog(QDialog):
    def __init__(self, video_path: str, duration: float, default_start: float,
                 default_end: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Trim Video")
        self.setMinimumWidth(680)

        self._video_path = video_path
        self._start = max(0.0, min(default_start, duration))
        self._end = max(self._start, min(default_end, duration))

        # Thread-safe result queue: worker puts tmp path, poll timer reads it
        self._result_queue: queue.Queue[str] = queue.Queue()
        self._extracting = False
        self._pending_t: float | None = None

        # Poll timer — checks queue every 50ms in the main thread
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self._poll_result)
        self._poll_timer.start()

        # --- Preview: stacked (still frame / video widget) ---
        self._stack = QStackedWidget()
        self._stack.setFixedHeight(_PREVIEW_H)

        self._frame_label = QLabel("Loading...")
        self._frame_label.setAlignment(Qt.AlignCenter)
        self._frame_label.setStyleSheet("background: black; color: #888;")

        self._video_widget = QVideoWidget()
        self._audio_out = QAudioOutput()
        self._audio_out.setVolume(1.0)
        self._player = QMediaPlayer(self)
        self._player.setVideoOutput(self._video_widget)
        self._player.setAudioOutput(self._audio_out)
        self._player.setSource(QUrl.fromLocalFile(str(Path(video_path).resolve())))
        self._player.positionChanged.connect(self._on_position_changed)

        self._stack.addWidget(self._frame_label)   # 0
        self._stack.addWidget(self._video_widget)  # 1
        self._stack.setCurrentIndex(0)

        # --- Play button ---
        self._play_btn = QPushButton("▶  Play")
        self._play_btn.setFixedWidth(100)
        self._play_btn.clicked.connect(self._toggle_play)

        # --- Timeline ---
        self._timeline = TrimTimeline(duration, self._start, self._end)
        self._timeline.range_changed.connect(self._on_range_changed)
        self._timeline.handle_moved.connect(self._on_handle_moved)
        self._timeline.handle_released.connect(self._on_handle_released)
        self._timeline.playhead_scrubbed.connect(self._on_playhead_scrubbed)

        # --- Labels ---
        self._start_label = QLabel(self._fmt(self._start))
        self._start_label.setAlignment(Qt.AlignLeft)
        self._end_label = QLabel(self._fmt(self._end))
        self._end_label.setAlignment(Qt.AlignRight)
        for lbl in (self._start_label, self._end_label):
            f = lbl.font(); f.setPointSize(12); lbl.setFont(f)

        time_row = QHBoxLayout()
        time_row.addWidget(self._start_label)
        time_row.addStretch()
        time_row.addWidget(self._play_btn)
        time_row.addStretch()
        time_row.addWidget(self._end_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self._stack)
        layout.addSpacing(4)
        layout.addWidget(self._timeline)
        layout.addLayout(time_row)
        layout.addWidget(buttons)
        self.setLayout(layout)

        # Start initial frame extraction after dialog is laid out
        QTimer.singleShot(50, lambda: self._request_frame(self._start))

    def start_seconds(self) -> float:
        return self._start

    def end_seconds(self) -> float:
        return self._end

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._poll_timer.stop()
        super().closeEvent(event)

    # ------------------------------------------------------------------

    def _on_handle_moved(self, t: float) -> None:
        self._request_frame(t)

    def _on_handle_released(self, t: float) -> None:
        self._request_frame(t)

    def _on_range_changed(self, start: float, end: float) -> None:
        self._start = start
        self._end = end
        self._timeline.set_playhead(self._player.position() / 1000.0)
        self._start_label.setText(self._fmt(start))
        self._end_label.setText(self._fmt(end))
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
            self._stack.setCurrentIndex(0)
            self._play_btn.setText("▶  Play")

    def _on_playhead_scrubbed(self, t: float) -> None:
        pos_ms = int(t * 1000)
        self._player.setPosition(pos_ms)
        if self._player.playbackState() != QMediaPlayer.PlayingState:
            self._request_frame(t)

    def _request_frame(self, t: float) -> None:
        if self._extracting:
            self._pending_t = t
            return
        self._start_extraction(t)

    def _start_extraction(self, t: float) -> None:
        self._extracting = True
        self._pending_t = None
        video_path = self._video_path
        result_queue = self._result_queue

        def run():
            tmp = _extract_frame(video_path, t)
            result_queue.put(tmp)

        threading.Thread(target=run, daemon=True).start()

    def _poll_result(self) -> None:
        try:
            tmp = self._result_queue.get_nowait()
        except queue.Empty:
            return

        self._extracting = False

        if tmp:
            px = QPixmap(tmp)
            try:
                Path(tmp).unlink(missing_ok=True)
            except Exception:
                pass
            if not px.isNull():
                w = self._stack.width() or 640
                px = px.scaled(w, _PREVIEW_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._frame_label.setPixmap(px)
                self._frame_label.setText("")
                self._stack.setCurrentIndex(0)

        if self._pending_t is not None:
            self._start_extraction(self._pending_t)

    # --- Playback ---

    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
            self._play_btn.setText("▶  Play")
            self._stack.setCurrentIndex(0)
            self._request_frame(self._player.position() / 1000.0)
        else:
            self._stack.setCurrentIndex(1)
            pos = self._player.position()
            start_ms = int(self._start * 1000)
            end_ms = int(self._end * 1000)
            # Always start from trim start, unless already within the trim range
            if pos < start_ms or pos >= end_ms:
                self._player.setPosition(start_ms)
            self._player.play()
            self._play_btn.setText("⏸  Pause")

    def _on_position_changed(self, pos_ms: int) -> None:
        self._timeline.set_playhead(pos_ms / 1000.0)
        if (self._player.playbackState() == QMediaPlayer.PlayingState
                and pos_ms >= int(self._end * 1000)):
            self._player.pause()
            self._player.setPosition(int(self._end * 1000))
            self._play_btn.setText("▶  Play")
            self._stack.setCurrentIndex(0)
            self._request_frame(self._end)

    @staticmethod
    def _fmt(seconds: float) -> str:
        m = int(seconds) // 60
        s = seconds - m * 60
        return f"{m:02d}:{s:05.2f}"
