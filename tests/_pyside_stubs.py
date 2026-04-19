"""Shared PySide6 stubs for headless UI tests.

Importing this module installs minimal PySide6 replacements into
sys.modules so that app.ui.* can import cleanly without a real Qt
install. Safe to import repeatedly — install is idempotent.
"""

from __future__ import annotations

import sys
import types


class _BoundSignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot):
        self._slots.append(slot)

    def emit(self, *args, **kwargs):
        for slot in list(self._slots):
            slot(*args, **kwargs)


class Signal:
    def __init__(self, *_args, **_kwargs):
        self._name = ""

    def __set_name__(self, _owner, name):
        self._name = f"__sig_{name}"

    def __get__(self, instance, _owner):
        if instance is None:
            return self
        sig = getattr(instance, self._name, None)
        if sig is None:
            sig = _BoundSignal()
            setattr(instance, self._name, sig)
        return sig


def install_pyside6_stubs() -> None:
    if "PySide6" in sys.modules:
        return

    class Qt:
        LeftButton = 1
        Horizontal = 1
        Key_Space = 32
        WidgetWithChildrenShortcut = 0
        AlignCenter = 0
        AlignLeft = 0
        AlignRight = 0
        KeepAspectRatio = 0
        SmoothTransformation = 0
        SizeHorCursor = 0

    class QSignalBlocker:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class QTimer:
        timeout = _BoundSignal()

        def __init__(self, *_args, **_kwargs):
            self.started = 0
            self.stopped = 0

        def setInterval(self, _interval):
            pass

        def start(self):
            self.started += 1

        def stop(self):
            self.stopped += 1

        @staticmethod
        def singleShot(_ms, fn):
            fn()

    class QUrl:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def fromLocalFile(path):
            return path

    class QRect:
        def __init__(self, *_args, **_kwargs):
            pass

    class _Widget:
        def __init__(self, *_args, **_kwargs):
            self._w = 100
            self._h = 48
            self._parent = None
            self._visible = True
            self._enabled = True
            self._layout = None

        def setMinimumHeight(self, _h):
            pass

        def setMouseTracking(self, _enabled):
            pass

        def resize(self, w, h):
            self._w = w
            self._h = h

        def width(self):
            return self._w

        def height(self):
            return self._h

        def update(self):
            pass

        def setCursor(self, _cursor):
            pass

        def setParent(self, parent):
            self._parent = parent

        def deleteLater(self):
            pass

        def setVisible(self, visible):
            self._visible = visible

        def setEnabled(self, enabled):
            self._enabled = enabled

        def isEnabled(self):
            return self._enabled

        def setLayout(self, layout):
            self._layout = layout

        def layout(self):
            return self._layout

        def setAcceptDrops(self, _enabled):
            pass

    class _Layout:
        def __init__(self, *_args, **_kwargs):
            self._widgets = []

        def addWidget(self, widget, *_args, **_kwargs):
            self._widgets.append(widget)

        def addLayout(self, *_args, **_kwargs):
            pass

        def addStretch(self, *_args, **_kwargs):
            pass

        def addSpacing(self, *_args, **_kwargs):
            pass

        def setContentsMargins(self, *_args):
            pass

        def count(self):
            return len(self._widgets)

        def itemAt(self, i):
            w = self._widgets[i]
            return types.SimpleNamespace(widget=lambda: w)

        def takeAt(self, i):
            w = self._widgets.pop(i)
            return types.SimpleNamespace(widget=lambda: w)

        def removeWidget(self, widget):
            try:
                self._widgets.remove(widget)
            except ValueError:
                pass

    class QPushButton(_Widget):
        def __init__(self, *_args, **_kwargs):
            super().__init__()
            self.clicked = _BoundSignal()
            self._text = ""
            self._tooltip = ""

        def setText(self, text):
            self._text = text

        def setToolTip(self, tip):
            self._tooltip = tip

        def toolTip(self):
            return self._tooltip

    class QSlider(_Widget):
        def __init__(self, *_args, **_kwargs):
            super().__init__()
            self.sliderMoved = _BoundSignal()
            self.valueChanged = _BoundSignal()
            self._value = 100
            self._down = False

        def setRange(self, *_args):
            pass

        def setStyleSheet(self, *_args):
            pass

        def setValue(self, value):
            self._value = value

        def value(self):
            return self._value

        def isSliderDown(self):
            return self._down

    class QLabel(_Widget):
        def __init__(self, *_args, **_kwargs):
            super().__init__()

        def setText(self, _text):
            pass

        def setAlignment(self, _a):
            pass

        def setStyleSheet(self, _s):
            pass

        def setPixmap(self, _p):
            pass

        def font(self):
            return types.SimpleNamespace(setPointSize=lambda _x: None)

        def setFont(self, _font):
            pass

    class QGroupBox(_Widget):
        pass

    class QDialog(_Widget):
        pass

    class QStackedWidget(_Widget):
        def setFixedHeight(self, *_args):
            pass

        def addWidget(self, *_args):
            pass

        def setCurrentIndex(self, *_args):
            pass

    class QDialogButtonBox:
        Ok = 1
        Cancel = 2

        def __init__(self, *_args, **_kwargs):
            self.accepted = _BoundSignal()
            self.rejected = _BoundSignal()

    class QRadioButton(_Widget):
        def __init__(self, *_args, **_kwargs):
            super().__init__()
            self.toggled = _BoundSignal()
            self.clicked = _BoundSignal()
            self._checked = False
            self._auto_exclusive = True

        def setChecked(self, checked):
            changed = self._checked != checked
            self._checked = checked
            if changed:
                self.toggled.emit(checked)

        def isChecked(self):
            return self._checked

        def setAutoExclusive(self, value):
            self._auto_exclusive = value

    class QFileDialog:
        @staticmethod
        def getOpenFileName(*_args, **_kwargs):
            return ("", "")

        @staticmethod
        def getSaveFileName(*_args, **_kwargs):
            return ("", "")

    class QMessageBox:
        Yes = 1
        No = 2

        @staticmethod
        def warning(*_args, **_kwargs):
            return QMessageBox.Yes

        @staticmethod
        def information(*_args, **_kwargs):
            return QMessageBox.Yes

        @staticmethod
        def critical(*_args, **_kwargs):
            return QMessageBox.Yes

        @staticmethod
        def question(*_args, **_kwargs):
            return QMessageBox.Yes

    class QMainWindow(_Widget):
        def setWindowTitle(self, _t):
            pass

        def setCentralWidget(self, _w):
            pass

    class QLineEdit(_Widget):
        def __init__(self, *_args, **_kwargs):
            super().__init__()
            self._text = ""

        def setReadOnly(self, _v):
            pass

        def setPlaceholderText(self, _t):
            pass

        def setText(self, text):
            self._text = text

        def text(self):
            return self._text

    class QProgressBar(_Widget):
        def setRange(self, *_args):
            pass

        def setValue(self, *_args):
            pass

    class QAudioOutput:
        def __init__(self, *_args, **_kwargs):
            pass

        def setVolume(self, *_args):
            pass

    class QMediaPlayer:
        PlayingState = 1
        PausedState = 2
        StoppedState = 3

        def __init__(self, *_args, **_kwargs):
            self.durationChanged = _BoundSignal()
            self.positionChanged = _BoundSignal()
            self.playbackStateChanged = _BoundSignal()

        def setVideoOutput(self, *_args):
            pass

        def setAudioOutput(self, *_args):
            pass

        def setSource(self, *_args):
            pass

        def setPosition(self, *_args):
            pass

        def position(self):
            return 0

        def duration(self):
            return 0

        def play(self):
            pass

        def pause(self):
            pass

        def stop(self):
            pass

        def playbackState(self):
            return QMediaPlayer.PausedState

        def setParent(self, *_args):
            pass

        def deleteLater(self):
            pass

    class QVideoWidget(_Widget):
        pass

    class QThread:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            pass

    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.Signal = Signal
    qtcore.Qt = Qt
    qtcore.QSignalBlocker = QSignalBlocker
    qtcore.QTimer = QTimer
    qtcore.QUrl = QUrl
    qtcore.QRect = QRect
    qtcore.QThread = QThread

    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QKeySequence = lambda *_args, **_kwargs: None
    qtgui.QShortcut = lambda *_args, **_kwargs: types.SimpleNamespace(
        setContext=lambda *_a, **_k: None,
        activated=_BoundSignal(),
    )
    qtgui.QColor = lambda *_args, **_kwargs: None
    qtgui.QPainter = lambda *_args, **_kwargs: types.SimpleNamespace(
        setRenderHint=lambda *_a, **_k: None,
        fillRect=lambda *_a, **_k: None,
    )
    qtgui.QPixmap = lambda *_args, **_kwargs: types.SimpleNamespace(
        isNull=lambda: True,
        scaled=lambda *_a, **_k: None,
    )

    qtmm = types.ModuleType("PySide6.QtMultimedia")
    qtmm.QAudioOutput = QAudioOutput
    qtmm.QMediaPlayer = QMediaPlayer

    qtmmw = types.ModuleType("PySide6.QtMultimediaWidgets")
    qtmmw.QVideoWidget = QVideoWidget

    qtwidgets = types.ModuleType("PySide6.QtWidgets")
    qtwidgets.QWidget = _Widget
    qtwidgets.QGroupBox = QGroupBox
    qtwidgets.QHBoxLayout = _Layout
    qtwidgets.QVBoxLayout = _Layout
    qtwidgets.QGridLayout = _Layout
    qtwidgets.QLabel = QLabel
    qtwidgets.QPushButton = QPushButton
    qtwidgets.QSlider = QSlider
    qtwidgets.QDialog = QDialog
    qtwidgets.QDialogButtonBox = QDialogButtonBox
    qtwidgets.QStackedWidget = QStackedWidget
    qtwidgets.QRadioButton = QRadioButton
    qtwidgets.QFileDialog = QFileDialog
    qtwidgets.QMessageBox = QMessageBox
    qtwidgets.QMainWindow = QMainWindow
    qtwidgets.QLineEdit = QLineEdit
    qtwidgets.QProgressBar = QProgressBar

    pyside6 = types.ModuleType("PySide6")
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = qtcore
    sys.modules["PySide6.QtGui"] = qtgui
    sys.modules["PySide6.QtMultimedia"] = qtmm
    sys.modules["PySide6.QtMultimediaWidgets"] = qtmmw
    sys.modules["PySide6.QtWidgets"] = qtwidgets
