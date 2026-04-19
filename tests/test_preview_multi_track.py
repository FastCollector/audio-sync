"""
Stage 6A tests for PreviewPanel multi-track scheduling.

Focuses on `_sync_audio_players`: given a video clock and each external
track's effective offset, verify that each player is seeked/paused
independently in the right direction.
"""

from __future__ import annotations

from _pyside_stubs import install_pyside6_stubs

install_pyside6_stubs()

from PySide6.QtMultimedia import QMediaPlayer

from app.ui.preview_panel import PreviewPanel


class _FakePlayer:
    def __init__(self, *, state=QMediaPlayer.PausedState, position=0):
        self._state = state
        self._position = position
        self.set_positions: list[int] = []
        self.play_calls = 0
        self.pause_calls = 0
        self.stop_calls = 0

    def playbackState(self):
        return self._state

    def position(self):
        return self._position

    def setPosition(self, pos):
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


def _panel_with_players(
    *,
    video_state: QMediaPlayer.PlaybackState,
    video_position: int,
    offsets_ms: dict[str, int],
    player_states: dict[str, QMediaPlayer.PlaybackState] | None = None,
    player_positions: dict[str, int] | None = None,
) -> PreviewPanel:
    panel = PreviewPanel.__new__(PreviewPanel)
    panel.video_player = _FakePlayer(state=video_state, position=video_position)
    panel._audio_players = {}
    panel._audio_offset_ms = dict(offsets_ms)
    player_states = player_states or {}
    player_positions = player_positions or {}
    for tid in offsets_ms:
        panel._audio_players[tid] = _FakePlayer(
            state=player_states.get(tid, QMediaPlayer.PausedState),
            position=player_positions.get(tid, 0),
        )
    return panel


def test_sync_audio_players_schedules_each_independently_when_video_playing():
    # video at t=5000ms; ext_A has offset 2000 → target 3000; ext_B offset -1000 → target 6000
    panel = _panel_with_players(
        video_state=QMediaPlayer.PlayingState,
        video_position=5_000,
        offsets_ms={"A": 2_000, "B": -1_000},
    )
    panel._sync_audio_players(force=True)

    assert panel._audio_players["A"].set_positions[-1] == 3_000
    assert panel._audio_players["B"].set_positions[-1] == 6_000
    assert panel._audio_players["A"].play_calls == 1
    assert panel._audio_players["B"].play_calls == 1


def test_sync_audio_players_pauses_track_with_negative_target():
    # video at t=500ms; ext_A has offset 2000 → target -1500 (before its start)
    panel = _panel_with_players(
        video_state=QMediaPlayer.PlayingState,
        video_position=500,
        offsets_ms={"A": 2_000},
    )
    panel._sync_audio_players(force=True)

    assert panel._audio_players["A"].pause_calls == 1
    assert panel._audio_players["A"].set_positions[-1] == 0


def test_sync_audio_players_skips_already_aligned_when_not_forced():
    # drift of 10ms, < 80ms threshold → no setPosition call
    panel = _panel_with_players(
        video_state=QMediaPlayer.PlayingState,
        video_position=5_000,
        offsets_ms={"A": 1_000},
        player_positions={"A": 4_010},  # target 4000, drift 10
        player_states={"A": QMediaPlayer.PlayingState},
    )
    panel._sync_audio_players(force=False)

    assert panel._audio_players["A"].set_positions == []
    assert panel._audio_players["A"].play_calls == 0  # already playing


def test_sync_audio_players_seeks_when_drift_exceeds_threshold():
    # drift > 80ms triggers setPosition
    panel = _panel_with_players(
        video_state=QMediaPlayer.PlayingState,
        video_position=5_000,
        offsets_ms={"A": 1_000},
        player_positions={"A": 4_200},  # target 4000, drift 200
        player_states={"A": QMediaPlayer.PlayingState},
    )
    panel._sync_audio_players(force=False)

    assert panel._audio_players["A"].set_positions[-1] == 4_000


def test_sync_audio_players_pauses_non_playing_externals_when_video_paused():
    # video paused → any externals currently playing must be paused.
    panel = _panel_with_players(
        video_state=QMediaPlayer.PausedState,
        video_position=5_000,
        offsets_ms={"A": 1_000},
        player_states={"A": QMediaPlayer.PlayingState},
    )
    panel._sync_audio_players(force=False)

    # The track's target = 4000; drift from 0 = 4000 > 80 → setPosition(4000) called
    # But since video is paused, no play() call.
    assert panel._audio_players["A"].play_calls == 0
    assert panel._audio_players["A"].pause_calls == 1


def test_sync_audio_players_noop_when_no_externals():
    panel = _panel_with_players(
        video_state=QMediaPlayer.PlayingState,
        video_position=5_000,
        offsets_ms={},
    )
    # Should not raise
    panel._sync_audio_players(force=True)
