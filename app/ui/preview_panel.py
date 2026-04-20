from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class TrackSpec:
    """Describes one audio track for preview playback.

    `effective_offset_sec` is the track's master-aligned offset relative to
    the video clock:  (track.offset_to_master - embedded.offset_to_master).
    The embedded track has effective_offset_sec == 0 by definition and
    `path` is ignored — it is rendered by the video_player itself.
    """

    track_id: str
    display_name: str
    is_embedded: bool
    path: str | None
    effective_offset_sec: float
    volume: float = 1.0


class PreviewPanel(QGroupBox):
    """Preview: video + N synchronized audio tracks.

    - video_player renders video; its audio is the embedded track.
    - Each non-embedded track has its own QMediaPlayer/QAudioOutput.
    - Per-track volume sliders are rebuilt on configure_tracks().
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Preview", parent)

        self.video_path: str | None = None
        self._trim_start_ms: int | None = None
        self._trim_end_ms: int | None = None

        # Per-track state keyed by track_id.
        self._audio_players: dict[str, QMediaPlayer] = {}
        self._audio_outputs: dict[str, QAudioOutput] = {}
        self._audio_offset_ms: dict[str, int] = {}
        self._audio_paths: dict[str, str] = {}
        self._embedded_track_id: str | None = None

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(260)

        self.video_output = QAudioOutput()
        self.video_output.setVolume(1.0)

        self.video_player = QMediaPlayer(self)
        self.video_player.setVideoOutput(self.video_widget)
        self.video_player.setAudioOutput(self.video_output)

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

        self.state_label = QLabel("Load files and run Sync to enable preview")
        self.play_pause_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.play_pause_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self.play_pause_shortcut.activated.connect(self._on_space_pressed)

        controls = QHBoxLayout()
        controls.addWidget(self.play_pause_btn)
        controls.addWidget(self.seek_slider, stretch=1)
        controls.addWidget(self.time_label)

        # Volume rows get rebuilt on every configure_tracks().
        self._mixer_host = QWidget()
        self._mixer_layout = QVBoxLayout()
        self._mixer_layout.setContentsMargins(0, 0, 0, 0)
        self._mixer_host.setLayout(self._mixer_layout)
        self._volume_sliders: dict[str, QSlider] = {}
        self._volume_rows: list[QWidget] = []

        root = QVBoxLayout()
        root.addWidget(self.video_widget)
        root.addLayout(controls)
        root.addWidget(self._mixer_host)
        root.addWidget(self.state_label)
        self.setLayout(root)

        self.video_player.durationChanged.connect(self._on_duration_changed)
        self.video_player.positionChanged.connect(self._on_video_position_changed)
        self.video_player.playbackStateChanged.connect(self._on_video_state_changed)

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(60)
        self._sync_timer.timeout.connect(self._sync_audio_players)

        self.set_enabled(False)

    # ------------------------------------------------------------------
    # Configuration

    def configure_tracks(
        self,
        video_path: str,
        tracks: list[TrackSpec],
        *,
        trim_start: float | None = None,
        trim_end: float | None = None,
    ) -> None:
        self.stop()

        self.video_path = video_path
        self._trim_start_ms = int(trim_start * 1000) if trim_start is not None else None
        self._trim_end_ms = int(trim_end * 1000) if trim_end is not None else None

        self.video_player.setSource(QUrl.fromLocalFile(str(Path(video_path).resolve())))

        self._reset_audio_players()
        self._rebuild_mixer(tracks)

        if self._trim_start_ms is not None:
            self.video_player.setPosition(self._trim_start_ms)

        self.state_label.setText(f"Preview ready ({len(tracks)} tracks)")
        self.set_enabled(True)

    def clear(self) -> None:
        self.stop()
        self.video_path = None
        self._trim_start_ms = None
        self._trim_end_ms = None
        self._reset_audio_players()
        self._rebuild_mixer([])
        self.video_player.setSource(QUrl())
        self.state_label.setText("Load files and run Sync to enable preview")
        self.seek_slider.setRange(0, 0)
        self.time_label.setText("00:00 / 00:00")
        self.set_enabled(False)

    def volumes(self) -> dict[str, float]:
        """Current per-track volume in [0.0, 1.0] keyed by track_id."""
        return {tid: slider.value() / 100.0 for tid, slider in self._volume_sliders.items()}

    # ------------------------------------------------------------------
    # Playback control

    def set_enabled(self, enabled: bool) -> None:
        self.play_pause_btn.setEnabled(enabled)
        self.seek_slider.setEnabled(enabled)
        for slider in self._volume_sliders.values():
            slider.setEnabled(enabled)

    def toggle_play_pause(self) -> None:
        if self.video_player.playbackState() == QMediaPlayer.PlayingState:
            self.video_player.pause()
            for p in self._audio_players.values():
                p.pause()
            self._sync_timer.stop()
            return

        start = self._trim_start_ms or 0
        pos = self.video_player.position()
        end = self._trim_end_ms if self._trim_end_ms is not None else self.video_player.duration()
        if pos < start or pos >= end:
            self.video_player.setPosition(start)

        self.video_player.play()
        self._sync_audio_players(force=True)
        self._sync_timer.start()

    def _on_space_pressed(self) -> None:
        if self.play_pause_btn.isEnabled():
            self.toggle_play_pause()

    def stop(self) -> None:
        self._sync_timer.stop()
        self.video_player.stop()
        for p in self._audio_players.values():
            p.stop()

    def _seek_to(self, position_ms: int) -> None:
        start = self._trim_start_ms or 0
        end = self._trim_end_ms if self._trim_end_ms is not None else self.video_player.duration()
        position_ms = max(start, min(end, position_ms))
        self.video_player.setPosition(position_ms)
        self._sync_audio_players(force=True)

    # ------------------------------------------------------------------
    # Video player callbacks

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
        if self._trim_end_ms is not None:
            if (self.video_player.playbackState() == QMediaPlayer.PlayingState
                    and position_ms >= self._trim_end_ms):
                self.video_player.pause()
                self.video_player.setPosition(self._trim_end_ms)
                for p in self._audio_players.values():
                    p.pause()
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
            for p in self._audio_players.values():
                p.stop()
        else:
            for p in self._audio_players.values():
                p.pause()

    # ------------------------------------------------------------------
    # Audio sync

    def _sync_audio_players(self, force: bool = False) -> None:
        if not self._audio_players:
            return

        video_pos = self.video_player.position()
        video_playing = self.video_player.playbackState() == QMediaPlayer.PlayingState

        for tid, player in self._audio_players.items():
            target = video_pos - self._audio_offset_ms[tid]

            if target < 0:
                if (
                    force
                    or player.playbackState() != QMediaPlayer.PausedState
                    or player.position() != 0
                ):
                    player.pause()
                    player.setPosition(0)
                continue

            drift_ms = abs(player.position() - target)
            if force or drift_ms > 80:
                player.setPosition(target)

            if video_playing:
                if player.playbackState() != QMediaPlayer.PlayingState:
                    player.play()
            elif player.playbackState() == QMediaPlayer.PlayingState:
                player.pause()

    # ------------------------------------------------------------------
    # Internal helpers

    def _reset_audio_players(self) -> None:
        for p in self._audio_players.values():
            p.stop()
            p.setSource(QUrl())
            p.setParent(None)
            p.deleteLater()
        self._audio_players.clear()
        self._audio_outputs.clear()
        self._audio_offset_ms.clear()
        self._audio_paths.clear()
        self._embedded_track_id = None

    def _rebuild_mixer(self, tracks: list[TrackSpec]) -> None:
        for row in self._volume_rows:
            self._mixer_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._volume_rows.clear()
        self._volume_sliders.clear()

        for spec in tracks:
            row = self._build_mixer_row(spec)
            self._mixer_layout.addWidget(row)
            self._volume_rows.append(row)

            if spec.is_embedded:
                self._embedded_track_id = spec.track_id
                self.video_output.setVolume(spec.volume)
                continue

            assert spec.path is not None, "external track must have path"
            output = QAudioOutput()
            output.setVolume(spec.volume)
            player = QMediaPlayer(self)
            player.setAudioOutput(output)
            player.setSource(QUrl.fromLocalFile(str(Path(spec.path).resolve())))
            self._audio_outputs[spec.track_id] = output
            self._audio_players[spec.track_id] = player
            self._audio_offset_ms[spec.track_id] = int(round(spec.effective_offset_sec * 1000))
            self._audio_paths[spec.track_id] = spec.path

    def _build_mixer_row(self, spec: TrackSpec) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(
            f"{spec.display_name} [{'video' if spec.is_embedded else 'external'}]"
        )
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(int(round(spec.volume * 100)))

        if spec.is_embedded:
            slider.valueChanged.connect(
                lambda v: self.video_output.setVolume(v / 100.0)
            )
        else:
            tid = spec.track_id
            slider.valueChanged.connect(
                lambda v, _tid=tid: self._audio_outputs[_tid].setVolume(v / 100.0)
            )

        layout.addWidget(label)
        layout.addWidget(slider, stretch=1)
        row.setLayout(layout)
        self._volume_sliders[spec.track_id] = slider
        return row

    @staticmethod
    def _format_time(ms: int) -> str:
        total_seconds = max(ms, 0) // 1000
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _update_time_label(self, current_ms: int, total_ms: int) -> None:
        self.time_label.setText(
            f"{self._format_time(current_ms)} / {self._format_time(total_ms)}"
        )
