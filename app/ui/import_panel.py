from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}
WAV_EXTENSIONS = {".wav"}


class ImportPanel(QGroupBox):
    sync_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Import", parent)

        self.video_path_edit = QLineEdit()
        self.video_path_edit.setReadOnly(True)

        self.audio_path_edit = QLineEdit()
        self.audio_path_edit.setReadOnly(True)

        self.sync_button = QPushButton("Sync")
        self.sync_button.clicked.connect(self.sync_requested.emit)

        self.offset_label = QLabel("Offset: not computed")
        self.confidence_label = QLabel("Confidence: n/a")

        video_btn = QPushButton("Choose Video")
        video_btn.clicked.connect(self._pick_video)

        audio_btn = QPushButton("Choose WAV")
        audio_btn.clicked.connect(self._pick_audio)

        grid = QGridLayout()
        grid.addWidget(QLabel("Video A"), 0, 0)
        grid.addWidget(self.video_path_edit, 0, 1)
        grid.addWidget(video_btn, 0, 2)
        grid.addWidget(QLabel("Audio B"), 1, 0)
        grid.addWidget(self.audio_path_edit, 1, 1)
        grid.addWidget(audio_btn, 1, 2)

        footer = QHBoxLayout()
        footer.addWidget(self.sync_button)
        footer.addWidget(self.offset_label)
        footer.addWidget(self.confidence_label)

        root = QVBoxLayout()
        root.addLayout(grid)
        root.addLayout(footer)
        self.setLayout(root)

    def video_path(self) -> str:
        return self.video_path_edit.text().strip()

    def audio_path(self) -> str:
        return self.audio_path_edit.text().strip()

    def set_sync_result(self, offset: float, confidence: float) -> None:
        direction = "after" if offset >= 0 else "before"
        self.offset_label.setText(
            f"Offset: audio B starts {abs(offset):.3f}s {direction} video"
        )
        self.confidence_label.setText(f"Confidence: {confidence:.3f}")

    def clear_sync_result(self) -> None:
        self.offset_label.setText("Offset: not computed")
        self.confidence_label.setText("Confidence: n/a")

    def _pick_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.avi)",
        )
        if path:
            self.video_path_edit.setText(path)

    def _pick_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select External WAV",
            "",
            "WAV Files (*.wav)",
        )
        if path:
            self.audio_path_edit.setText(path)

    @staticmethod
    def is_supported_video(path: str) -> bool:
        return Path(path).suffix.lower() in VIDEO_EXTENSIONS

    @staticmethod
    def is_supported_audio(path: str) -> bool:
        return Path(path).suffix.lower() in WAV_EXTENSIONS
