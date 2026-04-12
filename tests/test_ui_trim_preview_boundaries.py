from __future__ import annotations

import sys
import types

import pytest


def _install_pyside6_stubs() -> None:
    if "PySide6" in sys.modules:
        return

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

    class _Layout:
        def addWidget(self, *_args, **_kwargs):
            pass

        def addLayout(self, *_args, **_kwargs):
            pass

        def addStretch(self, *_args, **_kwargs):
            pass

        def addSpacing(self, *_args, **_kwargs):
            pass

    class QPushButton:
        def __init__(self, *_args, **_kwargs):
            self.clicked = _BoundSignal()

        def setEnabled(self, _enabled):
            pass

        def setText(self, _text):
            pass

    class QSlider:
        def __init__(self, *_args, **_kwargs):
            self.sliderMoved = _BoundSignal()
            self.valueChanged = _BoundSignal()
            self._down = False

        def setRange(self, *_args):
            pass

        def setMinimumHeight(self, *_args):
            pass

        def setStyleSheet(self, *_args):
            pass

        def setValue(self, _value):
            pass

        def setEnabled(self, _enabled):
            pass

        def isSliderDown(self):
            return self._down

    class QLabel:
        def __init__(self, *_args, **_kwargs):
            pass

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
        def setLayout(self, _layout):
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

    class QAudioOutput:
        def setVolume(self, *_args):
            pass

    class QMediaPlayer:
        PlayingState = 1
        PausedState = 2
        StoppedState = 3

    class QVideoWidget(_Widget):
        pass

    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.Signal = Signal
    qtcore.Qt = Qt
    qtcore.QSignalBlocker = QSignalBlocker
    qtcore.QTimer = QTimer
    qtcore.QUrl = QUrl
    qtcore.QRect = QRect

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
    qtwidgets.QLabel = QLabel
    qtwidgets.QPushButton = QPushButton
    qtwidgets.QSlider = QSlider
    qtwidgets.QDialog = QDialog
    qtwidgets.QDialogButtonBox = QDialogButtonBox
    qtwidgets.QStackedWidget = QStackedWidget

    pyside6 = types.ModuleType("PySide6")
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = qtcore
    sys.modules["PySide6.QtGui"] = qtgui
    sys.modules["PySide6.QtMultimedia"] = qtmm
    sys.modules["PySide6.QtMultimediaWidgets"] = qtmmw
    sys.modules["PySide6.QtWidgets"] = qtwidgets


_install_pyside6_stubs()

from PySide6.QtMultimedia import QMediaPlayer

from app.ui.preview_panel import PreviewPanel
from app.ui.trim_dialog import TrimTimeline


class _FakePlayer:
    def __init__(self, *, state: QMediaPlayer.PlaybackState, position: int = 0, duration: int = 10_000):
        self._state = state
        self._position = position
        self._duration = duration
        self.set_positions: list[int] = []
        self.play_calls = 0
        self.pause_calls = 0
        self.stop_calls = 0

    def playbackState(self):
        return self._state

    def position(self):
        return self._position

    def duration(self):
        return self._duration

    def setPosition(self, pos: int):
        self._position = pos
        self.set_positions.append(pos)

    def play(self):
        self.play_calls += 1
        self._state = QMediaPlayer.PlayingState

    def pause(self):
        self.pause_calls += 1
        self._state = QMediaPlayer.PausedState

    def stop(self):
        self.stop_calls += 1
        self._state = QMediaPlayer.StoppedState


class _FakeTimer:
    def __init__(self):
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


class _FakeSlider:
    def __init__(self):
        self.value = None
        self.slider_down = False

    def isSliderDown(self):
        return self.slider_down

    def setValue(self, value: int):
        self.value = value


def _make_preview_panel_for_logic(*, position: int, start: int, end: int, state: QMediaPlayer.PlaybackState):
    panel = PreviewPanel.__new__(PreviewPanel)
    panel.video_player = _FakePlayer(state=state, position=position, duration=12_000)
    panel.external_player = _FakePlayer(state=state)
    panel._sync_timer = _FakeTimer()
    panel.seek_slider = _FakeSlider()
    panel._trim_start_ms = start
    panel._trim_end_ms = end
    panel.offset_ms = 0
    panel.audio_path = "audio.wav"
    panel._sync_external_player = lambda force=False: None
    panel._update_time_label = lambda _pos, _end: None
    return panel


def test_preview_play_jumps_to_trim_start_when_outside_trim_range_lower_bound():
    panel = _make_preview_panel_for_logic(
        position=500,
        start=1_000,
        end=8_000,
        state=QMediaPlayer.PausedState,
    )

    panel.toggle_play_pause()

    assert panel.video_player.set_positions[-1] == 1_000
    assert panel.video_player.play_calls == 1


def test_preview_play_jumps_to_trim_start_when_outside_trim_range_upper_bound():
    panel = _make_preview_panel_for_logic(
        position=8_000,
        start=1_000,
        end=8_000,
        state=QMediaPlayer.PausedState,
    )

    panel.toggle_play_pause()

    assert panel.video_player.set_positions[-1] == 1_000
    assert panel.video_player.play_calls == 1


def test_preview_playback_stops_and_clamps_at_trim_end():
    panel = _make_preview_panel_for_logic(
        position=2_000,
        start=1_000,
        end=5_000,
        state=QMediaPlayer.PlayingState,
    )

    panel._on_video_position_changed(5_250)

    assert panel.video_player.pause_calls == 1
    assert panel.external_player.pause_calls == 1
    assert panel.video_player.set_positions[-1] == 5_000
    assert panel._sync_timer.stopped == 1
    assert panel.seek_slider.value == 5_000


def test_preview_seek_clamps_to_trim_bounds():
    panel = _make_preview_panel_for_logic(
        position=2_000,
        start=1_000,
        end=5_000,
        state=QMediaPlayer.PausedState,
    )

    panel._seek_to(250)
    panel._seek_to(5_600)

    assert panel.video_player.set_positions[0] == 1_000
    assert panel.video_player.set_positions[1] == 5_000


def test_trim_timeline_playhead_scrub_does_not_move_handles():
    timeline = TrimTimeline(duration=10.0, initial_start=2.0, initial_end=8.0)
    timeline.resize(200, 48)

    initial_start = timeline.start()
    initial_end = timeline.end()
    scrubbed: list[float] = []
    timeline.playhead_scrubbed.connect(scrubbed.append)

    timeline._dragging = "playhead"
    timeline._update(150)

    assert timeline.start() == initial_start
    assert timeline.end() == initial_end
    assert len(scrubbed) == 1


def test_trim_timeline_releasing_playhead_does_not_emit_handle_released():
    timeline = TrimTimeline(duration=10.0, initial_start=2.0, initial_end=8.0)
    released: list[float] = []
    timeline.handle_released.connect(released.append)

    timeline._dragging = "playhead"
    timeline.mouseReleaseEvent(object())

    assert released == []
