"""Phase 2 GUI entrypoint for audio-sync."""

import os
import sys

# Disable numba JIT so librosa uses plain numpy — avoids a 10-second
# recompilation pause on first run inside a PyInstaller bundle.
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(900, 260)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
