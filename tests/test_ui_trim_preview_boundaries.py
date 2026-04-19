from __future__ import annotations

from _pyside_stubs import install_pyside6_stubs

install_pyside6_stubs()

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
    ext_player = _FakePlayer(state=state)
    panel._audio_players = {"ext1": ext_player}
    panel._audio_outputs = {}
    panel._audio_offset_ms = {"ext1": 0}
    panel._audio_paths = {"ext1": "audio.wav"}
    panel._embedded_track_id = None
    panel._sync_timer = _FakeTimer()
    panel.seek_slider = _FakeSlider()
    panel._trim_start_ms = start
    panel._trim_end_ms = end
    panel._sync_audio_players = lambda force=False: None
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

    ext_player = panel._audio_players["ext1"]
    assert panel.video_player.pause_calls == 1
    assert ext_player.pause_calls == 1
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
