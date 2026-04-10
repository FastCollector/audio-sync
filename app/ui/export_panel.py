from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QWidget,
)


class ExportPanel(QGroupBox):
    export_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Export", parent)

        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Choose output file")

        output_btn = QPushButton("Browse")
        output_btn.clicked.connect(self._pick_output)

        self.export_button = QPushButton("Export")
        self.export_button.clicked.connect(self.export_requested.emit)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)

        grid = QGridLayout()
        grid.addWidget(self.output_path_edit, 0, 0)
        grid.addWidget(output_btn, 0, 1)
        grid.addWidget(self.export_button, 1, 0)
        grid.addWidget(self.progress, 1, 1)
        self.setLayout(grid)

    def output_path(self) -> str:
        return self.output_path_edit.text().strip()

    def set_busy(self, busy: bool) -> None:
        if busy:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)

    def reset_progress(self) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(0)

    def _pick_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Synced Video",
            "",
            "Video Files (*.mp4 *.mov *.mkv *.avi)",
        )
        if path:
            self.output_path_edit.setText(path)
