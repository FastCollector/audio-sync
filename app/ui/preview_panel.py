from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, QUrl
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class PreviewPanel(QGroupBox):
    """Preview video with original audio (track 0) and external audio B (track 1)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Preview", parent)

        self.video_path: str | None = None
        self.audio_path: str | None = None
        self.offset_ms = 0
        self._trim_start_ms: int | None = None
        self._trim_end_ms: int | None = None

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(260)

        self.video_output = QAudioOutput()
        self.video_output.setVolume(1.0)

        self.external_output = QAudioOutput()
        self.external_output.setVolume(1.0)

        self.video_player = QMediaPlayer(self)
        self.video_player.setVideoOutput(self.video_widget)
        self.video_player.setAudioOutput(self.video_output)

        self.external_player = QMediaPlayer(self)
        self.external_player.setAudioOutput(self.external_output)

        self.play_pause_btn = QPushButton("Play")
        self.play_pause_btn.clicked.connect(self.toggle_play_pause)

        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderMoved.connect(self._seek_to)
        self.seek_slider.setMinimumHeight(28)
        self.seek_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px;
                background: #444;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #f0a500;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 18px;
                height: 18px;
                margin: -6px 0;
                border-radius: 9px;
                background: white;
                border: 2px solid #ccc;
            }
            QSlider::handle:horizontal:hover {
                background: #f0a500;
                border-color: #f0a500;
            }
        """)

        self.time_label = QLabel("00:00 / 00:00")

        self.video_volume = QSlider(Qt.Horizontal)
        self.video_volume.setRange(0, 100)
        self.video_volume.setValue(100)
        self.video_volume.valueChanged.connect(
            lambda value: self.video_output.setVolume(value / 100.0)
        )

        self.external_volume = QSlider(Qt.Horizontal)
        self.external_volume.setRange(0, 100)
        self.external_volume.setValue(100)
        self.external_volume.valueChanged.connect(
            lambda value: self.external_output.setVolume(value / 100.0)
        )

        self.state_label = QLabel("Load files and run Sync to enable preview")
        self.play_pause_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.play_pause_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.play_pause_shortcut.activated.connect(self._on_space_pressed)

        controls = QHBoxLayout()
        controls.addWidget(self.play_pause_btn)
        controls.addWidget(self.seek_slider, stretch=1)
        controls.addWidget(self.time_label)

        volumes = QHBoxLayout()
        volumes.addWidget(QLabel("Video audio (track 0)"))
        volumes.addWidget(self.video_volume, stretch=1)
        volumes.addSpacing(12)
        volumes.addWidget(QLabel("External audio B (track 1)"))
        volumes.addWidget(self.external_volume, stretch=1)

        root = QVBoxLayout()
        root.addWidget(self.video_widget)
        root.addLayout(controls)
        root.addLayout(volumes)
        root.addWidget(self.state_label)
        self.setLayout(root)

        self.video_player.durationChanged.connect(self._on_duration_changed)
        self.video_player.positionChanged.connect(self._on_video_position_changed)
        self.video_player.playbackStateChanged.connect(self._on_video_state_changed)

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(60)
        self._sync_timer.timeout.connect(self._sync_external_player)

        self.set_enabled(False)

    def configure(
        self,
        video_path: str,
        audio_path: str,
        offset_seconds: float,
        trim_start: float | None = None,
        trim_end: float | None = None,
    ) -> None:
        self.stop()

        self.video_path = video_path
        self.audio_path = audio_path
        self.offset_ms = int(round(offset_seconds * 1000.0))
        self._trim_start_ms = int(trim_start * 1000) if trim_start is not None else None
        self._trim_end_ms = int(trim_end * 1000) if trim_end is not None else None

        self.video_player.setSource(QUrl.fromLocalFile(str(Path(video_path).resolve())))
        self.external_player.setSource(QUrl.fromLocalFile(str(Path(audio_path).resolve())))

        if self._trim_start_ms is not None:
            self.video_player.setPosition(self._trim_start_ms)

        self.state_label.setText(f"Preview ready (offset: {offset_seconds:+.3f}s)")
        self.set_enabled(True)

    def clear(self) -> None:
        self.stop()
        self.video_path = None
        self.audio_path = None
        self.offset_ms = 0
        self._trim_start_ms = None
        self._trim_end_ms = None
        self.video_player.setSource(QUrl())
        self.external_player.setSource(QUrl())
        self.state_label.setText("Load files and run Sync to enable preview")
        self.seek_slider.setRange(0, 0)
        self.time_label.setText("00:00 / 00:00")
        self.set_enabled(False)

    def set_enabled(self, enabled: bool) -> None:
        self.play_pause_btn.setEnabled(enabled)
        self.seek_slider.setEnabled(enabled)
        self.video_volume.setEnabled(enabled)
        self.external_volume.setEnabled(enabled)

    def toggle_play_pause(self) -> None:
        if self.video_player.playbackState() == QMediaPlayer.PlayingState:
            self.video_player.pause()
            self.external_player.pause()
            self._sync_timer.stop()
            return

        start = self._trim_start_ms or 0
        pos = self.video_player.position()
        end = self._trim_end_ms if self._trim_end_ms is not None else self.video_player.duration()
        if pos < start or pos >= end:
            self.video_player.setPosition(start)

        self.video_player.play()
        self._sync_external_player(force=True)
        self._sync_timer.start()

    def _on_space_pressed(self) -> None:
        if self.play_pause_btn.isEnabled():
            self.toggle_play_pause()

    def stop(self) -> None:
        self._sync_timer.stop()
        self.video_player.stop()
        self.external_player.stop()

    def _seek_to(self, position_ms: int) -> None:
        start = self._trim_start_ms or 0
        end = self._trim_end_ms if self._trim_end_ms is not None else self.video_player.duration()
        position_ms = max(start, min(end, position_ms))
        self.video_player.setPosition(position_ms)
        self._sync_external_player(force=True)

    def _on_duration_changed(self, duration_ms: int) -> None:
        start = self._trim_start_ms or 0
        end = self._trim_end_ms if self._trim_end_ms is not None else max(duration_ms, 0)
        with QSignalBlocker(self.seek_slider):
            self.seek_slider.setRange(start, end)
            self.seek_slider.setValue(start)
        if self._trim_start_ms is not None:
            self.video_player.setPosition(start)
        self._update_time_label(start, end)

    def _on_video_position_changed(self, position_ms: int) -> None:
        # Auto-stop at trim end
        if self._trim_end_ms is not None:
            if (self.video_player.playbackState() == QMediaPlayer.PlayingState
                    and position_ms >= self._trim_end_ms):
                self.video_player.pause()
                self.video_player.setPosition(self._trim_end_ms)
                self.external_player.pause()
                self._sync_timer.stop()
                position_ms = self._trim_end_ms

        if self._trim_start_ms is not None and position_ms < self._trim_start_ms:
            position_ms = self._trim_start_ms

        if not self.seek_slider.isSliderDown():
            with QSignalBlocker(self.seek_slider):
                self.seek_slider.setValue(position_ms)
        duration = self.video_player.duration() or 1
        end = self._trim_end_ms if self._trim_end_ms is not None else duration
        self._update_time_label(position_ms, end)

    def _on_video_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlayingState:
            self.play_pause_btn.setText("Pause")
            self._sync_timer.start()
            return

        self.play_pause_btn.setText("Play")
        self._sync_timer.stop()
        if state == QMediaPlayer.StoppedState:
            self.external_player.stop()
        else:
            self.external_player.pause()

    def _sync_external_player(self, force: bool = False) -> None:
        if self.audio_path is None:
            return

        video_pos = self.video_player.position()
        target_external_pos = video_pos - self.offset_ms

        if target_external_pos < 0:
            if (
                force
                or self.external_player.playbackState() != QMediaPlayer.PausedState
                or self.external_player.position() != 0
            ):
                self.external_player.pause()
                self.external_player.setPosition(0)
            return

        drift_ms = abs(self.external_player.position() - target_external_pos)
        if force or drift_ms > 80:
            self.external_player.setPosition(target_external_pos)

        if self.video_player.playbackState() == QMediaPlayer.PlayingState:
            if self.external_player.playbackState() != QMediaPlayer.PlayingState:
                self.external_player.play()
        elif self.external_player.playbackState() == QMediaPlayer.PlayingState:
            self.external_player.pause()

    @staticmethod
    def _format_time(ms: int) -> str:
        total_seconds = max(ms, 0) // 1000
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _update_time_label(self, current_ms: int, total_ms: int) -> None:
        self.time_label.setText(
            f"{self._format_time(current_ms)} / {self._format_time(total_ms)}"
        )
