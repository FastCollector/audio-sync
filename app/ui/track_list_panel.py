"""
Stage 6A: multi-track list UI.

One row per AudioTrack in the project:
    [●] display_name  [kind]  offset=…  conf=…  [Remove]

The panel is a pure view over Project state. MainWindow mutates the
Project and calls `refresh(project)` to rerender. All row actions are
expressed as signals:

    add_external_requested(path: str)
    remove_track_requested(track_id: str)
    master_changed(track_id: str)

Remove is disabled for the embedded track and for the current master
(user must pick a different master before deleting the old one).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app.core.project import AudioTrack, Project, SourceKind

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac"}


class TrackListPanel(QGroupBox):
    add_external_requested = Signal(str)
    remove_track_requested = Signal(str)
    master_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Tracks", parent)

        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_host.setLayout(self._rows_layout)

        self._empty_label = QLabel("No tracks yet — import video + audio and Sync to begin.")

        self._add_btn = QPushButton("Add External Audio")
        self._add_btn.setEnabled(False)
        self._add_btn.clicked.connect(self._pick_and_add)

        root = QVBoxLayout()
        root.addWidget(self._empty_label)
        root.addWidget(self._rows_host)
        root.addWidget(self._add_btn)
        self.setLayout(root)

        self._row_widgets: list[QWidget] = []

    def refresh(self, project: Project | None) -> None:
        for w in self._row_widgets:
            self._rows_layout.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self._row_widgets.clear()

        if project is None or not project.audio_tracks:
            self._empty_label.setVisible(True)
            self._add_btn.setEnabled(False)
            return

        self._empty_label.setVisible(False)
        for track in project.audio_tracks:
            row = self._build_row(project, track)
            self._rows_layout.addWidget(row)
            self._row_widgets.append(row)
        self._add_btn.setEnabled(project.video_asset is not None)

    def _build_row(self, project: Project, track: AudioTrack) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)

        is_master = project.master_track_id == track.id
        is_embedded = track.source_kind is SourceKind.VIDEO_EMBEDDED

        radio = QRadioButton()
        radio.setAutoExclusive(False)  # we manage exclusivity across rebuilds ourselves
        radio.setChecked(is_master)
        # Use `clicked` (user action only) so setChecked during refresh doesn't
        # re-emit master_changed and trigger an unwanted re-sync.
        radio.clicked.connect(
            lambda _checked=False, tid=track.id: self.master_changed.emit(tid)
        )

        kind_txt = "video" if is_embedded else "external"
        name_lbl = QLabel(track.display_name)
        kind_lbl = QLabel(f"[{kind_txt}]")

        offset_txt = (
            f"{track.offset_to_master:+.3f}s"
            if track.offset_to_master is not None
            else "—"
        )
        conf_txt = (
            f"{track.confidence:.2f}" if track.confidence is not None else "—"
        )
        offset_lbl = QLabel(f"offset: {offset_txt}")
        conf_lbl = QLabel(f"conf: {conf_txt}")

        remove_btn = QPushButton("Remove")
        remove_btn.setEnabled(not (is_embedded or is_master))
        remove_btn.clicked.connect(
            lambda _checked=False, tid=track.id: self.remove_track_requested.emit(tid)
        )

        layout.addWidget(radio)
        layout.addWidget(name_lbl)
        layout.addWidget(kind_lbl)
        layout.addWidget(offset_lbl)
        layout.addWidget(conf_lbl)
        layout.addStretch(1)
        layout.addWidget(remove_btn)
        row.setLayout(layout)
        return row

    def set_controls_enabled(self, enabled: bool) -> None:
        self._add_btn.setEnabled(enabled and self._add_btn.isEnabled())
        for w in self._row_widgets:
            w.setEnabled(enabled)

    def _pick_and_add(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Add External Audio", "", "Audio Files (*.wav *.mp3 *.flac)"
        )
        if path:
            self.add_external_requested.emit(path)

    @staticmethod
    def is_supported_audio(path: str) -> bool:
        return Path(path).suffix.lower() in AUDIO_EXTENSIONS
