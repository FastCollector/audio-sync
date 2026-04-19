from __future__ import annotations

import tempfile
from pathlib import Path

import soundfile as sf
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.core.extract_cache import ExtractCache
from app.core.extractor import _get_duration
from app.core.ffmpeg_utils import get_ffmpeg_executable
from app.core.length_checker import MismatchType, check_lengths
from app.core.project import AudioTrack, Project, SourceKind, VideoAsset
from app.core.project_export import export_project
from app.core.project_sync import sync_all_to_master
from app.core.sync_engine import compute_offset
from app.ui.export_panel import ExportPanel
from app.ui.import_panel import ImportPanel
from app.ui.preview_panel import PreviewPanel, TrackSpec
from app.ui.track_list_panel import TrackListPanel
from app.ui.trim_dialog import TrimDialog

CONFIDENCE_THRESHOLD = 0.5


class TaskThread(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn()
            self.done.emit(result)
        except Exception as exc:  # pragma: no cover - GUI exception path
            self.failed.emit(str(exc))


def _build_initial_project(video_path: str, audio_path: str) -> Project:
    """Construct a fresh single-video + single-external Project, pre-sync."""
    video_duration = _get_duration(get_ffmpeg_executable(), video_path)
    audio_duration = sf.info(audio_path).duration

    project = Project()
    project.video_asset = VideoAsset(
        path=video_path,
        duration_seconds=video_duration,
        has_embedded_audio=True,
    )
    embedded = AudioTrack(
        display_name="embedded",
        source_kind=SourceKind.VIDEO_EMBEDDED,
        source_path=video_path,
        duration_seconds=video_duration,
    )
    external = AudioTrack(
        display_name=Path(audio_path).stem,
        source_kind=SourceKind.EXTERNAL,
        source_path=audio_path,
        duration_seconds=audio_duration,
    )
    project.add_track(embedded)
    project.add_track(external)
    project.link_embedded_audio(embedded.id)
    project.set_master(embedded.id)
    return project


def _external_tracks(project: Project) -> list[AudioTrack]:
    return [t for t in project.audio_tracks if t.source_kind is SourceKind.EXTERNAL]


def _first_external(project: Project) -> AudioTrack | None:
    externals = _external_tracks(project)
    return externals[0] if externals else None


def _apply_length_mismatch_trim(project: Project) -> MismatchType:
    """
    Mirror the legacy `check_lengths` → trim mapping on project_trim_end for
    the single-external case:
        AUDIO_OVERFLOW → cap output at video duration.
        VIDEO_OVERFLOW → cap output at audio-B end (dialog may adjust).
    Returns the mismatch classification so the caller can drive dialogs.
    """
    assert project.video_asset is not None
    external = _first_external(project)
    assert external is not None
    mismatch = check_lengths(
        project.video_asset.duration_seconds,
        external.duration_seconds,
        external.offset_to_master or 0.0,
    )
    if mismatch.mismatch_type == MismatchType.AUDIO_OVERFLOW:
        project.project_trim_end = project.video_asset.duration_seconds
    elif mismatch.mismatch_type == MismatchType.VIDEO_OVERFLOW:
        project.project_trim_end = (
            (external.offset_to_master or 0.0) + external.duration_seconds
        )
    return mismatch.mismatch_type


def _build_track_specs(project: Project, volumes: dict[str, float]) -> list[TrackSpec]:
    """Convert Project audio tracks → preview TrackSpec list.

    `effective_offset_sec` lets the preview schedule each source's local
    time using only the video clock, without knowing who the master is:
        source_time = video_player.position() - effective_offset
    where effective_offset = track.offset_to_master - embedded.offset_to_master.
    """
    embedded = project.embedded_audio_track()
    embedded_offset = embedded.offset_to_master if embedded and embedded.offset_to_master is not None else 0.0

    specs: list[TrackSpec] = []
    for t in project.audio_tracks:
        is_embedded = embedded is not None and t.id == embedded.id
        track_offset = t.offset_to_master if t.offset_to_master is not None else 0.0
        effective = track_offset - embedded_offset
        specs.append(TrackSpec(
            track_id=t.id,
            display_name=t.display_name,
            is_embedded=is_embedded,
            path=None if is_embedded else t.source_path,
            effective_offset_sec=effective,
            volume=volumes.get(t.id, 1.0),
        ))
    return specs


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("audio-sync — Phase 4")

        self.import_panel = ImportPanel()
        self.track_list_panel = TrackListPanel()
        self.preview_panel = PreviewPanel()
        self.export_panel = ExportPanel()
        self.status_label = QLabel("Ready")

        layout = QVBoxLayout()
        layout.addWidget(self.import_panel)
        layout.addWidget(self.track_list_panel)
        layout.addWidget(self.preview_panel)
        layout.addWidget(self.export_panel)
        layout.addWidget(self.status_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.import_panel.sync_requested.connect(self._on_sync_requested)
        self.import_panel.import_error.connect(self._on_import_error)
        self.export_panel.export_requested.connect(self._on_export_requested)
        self.track_list_panel.add_external_requested.connect(self._on_add_external_requested)
        self.track_list_panel.remove_track_requested.connect(self._on_remove_track_requested)
        self.track_list_panel.master_changed.connect(self._on_master_changed)

        self._project: Project | None = None
        self._running_thread: TaskThread | None = None
        self._extract_cache = ExtractCache(
            Path(tempfile.mkdtemp(prefix="audio-sync-cache-"))
        )

    # ------------------------------------------------------------------
    # Sync (initial — triggered by ImportPanel Sync button)

    def _on_sync_requested(self) -> None:
        video_path = self.import_panel.video_path()
        audio_path = self.import_panel.audio_path()

        if not video_path or not audio_path:
            QMessageBox.warning(
                self, "Missing Files", "Select both video and audio B before syncing."
            )
            return

        if not self.import_panel.is_supported_video(video_path):
            QMessageBox.warning(self, "Invalid Video", "Video must be MP4, MOV, MKV, or AVI.")
            return

        if not self.import_panel.is_supported_audio(audio_path):
            QMessageBox.warning(self, "Invalid Audio", "Audio B must be WAV, MP3, or FLAC.")
            return

        self._set_busy("Syncing...")
        self.import_panel.clear_sync_result()
        self.preview_panel.clear()
        self._project = None
        self.track_list_panel.refresh(None)

        cache = self._extract_cache

        def task() -> Project:
            project = _build_initial_project(video_path, audio_path)
            sync_all_to_master(
                project,
                path_resolver=cache.resolver(project),
                compute_fn=compute_offset,
            )
            _apply_length_mismatch_trim(project)
            return project

        self._start_task(task, self._handle_initial_sync_success)

    # ------------------------------------------------------------------
    # Track-list operations (trigger background re-sync where needed)

    def _on_add_external_requested(self, path: str) -> None:
        if self._project is None:
            QMessageBox.warning(self, "No Project", "Run initial Sync before adding tracks.")
            return
        if not TrackListPanel.is_supported_audio(path):
            QMessageBox.warning(self, "Invalid Audio", "Audio must be WAV, MP3, or FLAC.")
            return

        try:
            duration = sf.info(path).duration
        except Exception as exc:
            QMessageBox.critical(self, "Could Not Read Audio", str(exc))
            return

        track = AudioTrack(
            display_name=Path(path).stem,
            source_kind=SourceKind.EXTERNAL,
            source_path=path,
            duration_seconds=duration,
        )
        self._project.add_track(track)
        self._refresh_ui_from_project()
        self._start_resync()

    def _on_remove_track_requested(self, track_id: str) -> None:
        if self._project is None:
            return
        self._project.remove_track(track_id)
        self._refresh_ui_from_project()

    def _on_master_changed(self, track_id: str) -> None:
        if self._project is None:
            return
        if self._project.master_track_id == track_id:
            return
        self._project.set_master(track_id)
        self._refresh_ui_from_project()
        self._start_resync()

    def _start_resync(self) -> None:
        project = self._project
        if project is None:
            return
        self._set_busy("Re-syncing...")
        cache = self._extract_cache

        def task() -> Project:
            sync_all_to_master(
                project,
                path_resolver=cache.resolver(project),
                compute_fn=compute_offset,
            )
            return project

        self._start_task(task, self._handle_resync_success)

    # ------------------------------------------------------------------
    # Export

    def _on_export_requested(self) -> None:
        if self._project is None:
            QMessageBox.warning(self, "Not Synced", "Run Sync before exporting.")
            return
        if not self._can_export():
            QMessageBox.warning(
                self, "Export Blocked",
                "Switch master back to video audio to export (coming in 6B).",
            )
            return

        output_path = self.export_panel.output_path()
        if not output_path:
            QMessageBox.warning(self, "Missing Output", "Choose an output path first.")
            return

        project = self._project
        volumes = self.preview_panel.volumes()

        self.status_label.setText("Exporting...")
        self.export_panel.export_button.setEnabled(False)
        self.import_panel.sync_button.setEnabled(False)
        self.export_panel.set_busy(True)

        def task() -> None:
            export_project(project, output_path, volumes=volumes)

        self._start_task(task, self._handle_export_success)

    # ------------------------------------------------------------------
    # Task plumbing

    def _start_task(self, task, on_done) -> None:
        self._running_thread = TaskThread(task)
        self._running_thread.done.connect(on_done)
        self._running_thread.failed.connect(self._handle_task_failure)
        self._running_thread.start()

    def _set_busy(self, status: str) -> None:
        self.status_label.setText(status)
        self.import_panel.sync_button.setEnabled(False)
        self.export_panel.export_button.setEnabled(False)
        self.track_list_panel.set_controls_enabled(False)

    # ------------------------------------------------------------------
    # Sync task callbacks

    def _handle_initial_sync_success(self, project: Project) -> None:
        self.import_panel.sync_button.setEnabled(True)
        self.track_list_panel.set_controls_enabled(True)

        external = _first_external(project)
        assert project.video_asset is not None and external is not None
        confidence = external.confidence or 0.0
        offset = external.offset_to_master or 0.0

        if confidence < CONFIDENCE_THRESHOLD:
            proceed = QMessageBox.warning(
                self,
                "Low Sync Confidence",
                (
                    f"Sync quality is low ({confidence:.3f}). "
                    "The recordings may not match. Proceed anyway?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if proceed != QMessageBox.Yes:
                self.status_label.setText("Sync canceled due to low confidence")
                self.import_panel.clear_sync_result()
                self._project = None
                self.preview_panel.clear()
                self.track_list_panel.refresh(None)
                self.export_panel.export_button.setEnabled(False)
                return

        mismatch = check_lengths(
            project.video_asset.duration_seconds,
            external.duration_seconds,
            offset,
        )

        if mismatch.mismatch_type == MismatchType.AUDIO_OVERFLOW:
            choice = QMessageBox.question(
                self,
                "Audio Overflow",
                (
                    "External audio extends beyond the video end.\n\n"
                    "Yes = trim extra audio\n"
                    "No = black-screen fill (not implemented; will trim)"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if choice == QMessageBox.No:
                QMessageBox.information(
                    self,
                    "Black Screen Fill",
                    "Black-screen fill is not implemented yet. Audio will be trimmed.",
                )

        if mismatch.mismatch_type == MismatchType.VIDEO_OVERFLOW:
            default_end = offset + external.duration_seconds
            dialog = TrimDialog(
                self.import_panel.video_path(),
                project.video_asset.duration_seconds,
                default_start=0.0,
                default_end=default_end,
                parent=self,
            )
            if dialog.exec() != QDialog.Accepted:
                self.status_label.setText("Sync canceled")
                self.import_panel.clear_sync_result()
                self._project = None
                self.preview_panel.clear()
                self.track_list_panel.refresh(None)
                self.export_panel.export_button.setEnabled(False)
                return
            project.project_trim_start = dialog.start_seconds() or None
            project.project_trim_end = dialog.end_seconds()

        self._project = project
        self.import_panel.set_sync_result(offset, confidence)
        self._refresh_ui_from_project()
        self.status_label.setText("Sync complete. Ready to export.")

    def _handle_resync_success(self, project: Project) -> None:
        self.import_panel.sync_button.setEnabled(True)
        self.track_list_panel.set_controls_enabled(True)
        primary = _first_external(project)
        if primary is not None and primary.offset_to_master is not None:
            self.import_panel.set_sync_result(
                primary.offset_to_master, primary.confidence or 0.0
            )
        self._refresh_ui_from_project()
        self.status_label.setText("Re-sync complete.")

    def _handle_export_success(self, _result: object) -> None:
        self.import_panel.sync_button.setEnabled(True)
        self.track_list_panel.set_controls_enabled(True)
        self.export_panel.export_button.setEnabled(self._can_export())
        self.export_panel.set_busy(False)
        self.status_label.setText("Export complete")
        QMessageBox.information(self, "Export Finished", "Video exported successfully.")

    def _handle_task_failure(self, error: str) -> None:
        self.import_panel.sync_button.setEnabled(True)
        self.track_list_panel.set_controls_enabled(True)
        self.export_panel.export_button.setEnabled(self._can_export())
        self.export_panel.set_busy(False)
        self.status_label.setText("Operation failed")
        QMessageBox.critical(self, "Operation Failed", error)

    def _on_import_error(self, message: str) -> None:
        QMessageBox.warning(self, "Unsupported Drop", message)

    # ------------------------------------------------------------------
    # UI refresh

    def _refresh_ui_from_project(self) -> None:
        project = self._project
        self.track_list_panel.refresh(project)

        if project is None or project.video_asset is None:
            self.preview_panel.clear()
            self.export_panel.export_button.setEnabled(False)
            return

        existing_volumes = self.preview_panel.volumes()
        specs = _build_track_specs(project, existing_volumes)
        self.preview_panel.configure_tracks(
            project.video_asset.path,
            specs,
            trim_start=project.project_trim_start,
            trim_end=project.project_trim_end,
        )

        export_ok = self._can_export()
        self.export_panel.export_button.setEnabled(export_ok)
        self.export_panel.export_button.setToolTip(
            "" if export_ok
            else "Switch master back to video audio to export (coming in 6B)"
        )

    def _can_export(self) -> bool:
        project = self._project
        if project is None:
            return False
        embedded = project.embedded_audio_track()
        if embedded is None:
            return False
        if project.master_track_id != embedded.id:
            return False
        if any(
            t.offset_to_master is None
            for t in project.audio_tracks
            if t.id != project.master_track_id
        ):
            return False
        return True
