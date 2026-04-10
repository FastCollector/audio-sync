from __future__ import annotations

import os
from dataclasses import dataclass

import soundfile as sf
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.core.exporter import export
from app.core.extractor import extract_audio
from app.core.length_checker import MismatchType, check_lengths
from app.core.sync_engine import compute_offset
from app.ui.export_panel import ExportPanel
from app.ui.import_panel import ImportPanel
from app.ui.preview_panel import PreviewPanel

CONFIDENCE_THRESHOLD = 0.5


@dataclass
class SyncResult:
    offset: float
    confidence: float
    video_duration: float
    audio_duration: float
    trim_audio_end: float | None
    trim_video_end: float | None


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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("audio-sync — Phase 4")

        self.import_panel = ImportPanel()
        self.preview_panel = PreviewPanel()
        self.export_panel = ExportPanel()
        self.status_label = QLabel("Ready")

        layout = QVBoxLayout()
        layout.addWidget(self.import_panel)
        layout.addWidget(self.preview_panel)
        layout.addWidget(self.export_panel)
        layout.addWidget(self.status_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.import_panel.sync_requested.connect(self._on_sync_requested)
        self.import_panel.import_error.connect(self._on_import_error)
        self.export_panel.export_requested.connect(self._on_export_requested)

        self._sync_result: SyncResult | None = None
        self._running_thread: TaskThread | None = None

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

        self.status_label.setText("Syncing...")
        self.import_panel.sync_button.setEnabled(False)
        self.export_panel.export_button.setEnabled(False)
        self.import_panel.clear_sync_result()
        self.preview_panel.clear()
        self._sync_result = None

        def task() -> SyncResult:
            ref_wav: str | None = None
            try:
                ref_wav, video_duration = extract_audio(video_path)
                offset, confidence = compute_offset(ref_wav, audio_path)
            finally:
                if ref_wav is not None and os.path.exists(ref_wav):
                    os.unlink(ref_wav)

            audio_duration = sf.info(audio_path).duration
            mismatch = check_lengths(video_duration, audio_duration, offset)
            trim_audio_end: float | None = None
            trim_video_end: float | None = None

            if mismatch.mismatch_type == MismatchType.AUDIO_OVERFLOW:
                trim_audio_end = video_duration - max(offset, 0.0)
            elif mismatch.mismatch_type == MismatchType.VIDEO_OVERFLOW:
                trim_video_end = offset + audio_duration

            return SyncResult(
                offset=offset,
                confidence=confidence,
                video_duration=video_duration,
                audio_duration=audio_duration,
                trim_audio_end=trim_audio_end,
                trim_video_end=trim_video_end,
            )

        self._running_thread = TaskThread(task)
        self._running_thread.done.connect(self._handle_sync_success)
        self._running_thread.failed.connect(self._handle_task_failure)
        self._running_thread.start()

    def _on_export_requested(self) -> None:
        if self._sync_result is None:
            QMessageBox.warning(self, "Not Synced", "Run Sync before exporting.")
            return

        output_path = self.export_panel.output_path()
        if not output_path:
            QMessageBox.warning(self, "Missing Output", "Choose an output path first.")
            return

        video_path = self.import_panel.video_path()
        audio_path = self.import_panel.audio_path()
        sync_result = self._sync_result

        self.status_label.setText("Exporting...")
        self.export_panel.export_button.setEnabled(False)
        self.import_panel.sync_button.setEnabled(False)
        self.export_panel.set_busy(True)

        def task() -> None:
            export(
                video_path,
                audio_path,
                sync_result.offset,
                output_path,
                trim_audio_end=sync_result.trim_audio_end,
                trim_video_end=sync_result.trim_video_end,
            )

        self._running_thread = TaskThread(task)
        self._running_thread.done.connect(self._handle_export_success)
        self._running_thread.failed.connect(self._handle_task_failure)
        self._running_thread.start()

    def _handle_sync_success(self, result: SyncResult) -> None:
        self.import_panel.sync_button.setEnabled(True)

        if result.confidence < CONFIDENCE_THRESHOLD:
            proceed = QMessageBox.warning(
                self,
                "Low Sync Confidence",
                (
                    f"Sync quality is low ({result.confidence:.3f}). "
                    "The recordings may not match. Proceed anyway?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if proceed != QMessageBox.Yes:
                self.status_label.setText("Sync canceled due to low confidence")
                self.import_panel.clear_sync_result()
                self._sync_result = None
                self.preview_panel.clear()
                self.export_panel.export_button.setEnabled(False)
                return

        if result.trim_audio_end is not None:
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

        if result.trim_video_end is not None:
            default_end = max(0.0, result.trim_video_end)
            value, ok = QInputDialog.getDouble(
                self,
                "Video Overflow",
                "Video extends beyond aligned audio. Choose video out-point (seconds):",
                value=default_end,
                minValue=0.0,
                maxValue=result.video_duration,
                decimals=3,
            )
            if not ok:
                self.status_label.setText("Sync canceled")
                self.import_panel.clear_sync_result()
                self._sync_result = None
                self.preview_panel.clear()
                self.export_panel.export_button.setEnabled(False)
                return
            result.trim_video_end = value

        self._sync_result = result
        self.export_panel.export_button.setEnabled(True)
        self.import_panel.set_sync_result(result.offset, result.confidence)
        self.preview_panel.configure(
            self.import_panel.video_path(), self.import_panel.audio_path(), result.offset
        )
        self.status_label.setText("Sync complete. Ready to export.")

    def _handle_export_success(self, _result: object) -> None:
        self.import_panel.sync_button.setEnabled(True)
        self.export_panel.export_button.setEnabled(True)
        self.export_panel.set_busy(False)
        self.status_label.setText("Export complete")
        QMessageBox.information(self, "Export Finished", "Video exported successfully.")

    def _handle_task_failure(self, error: str) -> None:
        self.import_panel.sync_button.setEnabled(True)
        self.export_panel.export_button.setEnabled(self._sync_result is not None)
        self.export_panel.set_busy(False)
        self.status_label.setText("Operation failed")
        QMessageBox.critical(self, "Operation Failed", error)

    def _on_import_error(self, message: str) -> None:
        QMessageBox.warning(self, "Unsupported Drop", message)
