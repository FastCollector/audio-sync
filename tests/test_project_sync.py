"""
Stage 2 tests for app.core.project_sync.

Pure orchestration. No real audio — compute_fn and path_resolver are
injected for every test.
"""

from __future__ import annotations

import pytest

from app.core.project import (
    AudioTrack,
    InvalidProjectState,
    Project,
    SourceKind,
)
from app.core.project_sync import sync_all_to_master


def _track(name: str, path: str) -> AudioTrack:
    return AudioTrack(
        display_name=name,
        source_kind=SourceKind.EXTERNAL,
        source_path=path,
        duration_seconds=10.0,
    )


def _project_with_master(*non_master_names: str) -> tuple[Project, AudioTrack, list[AudioTrack]]:
    p = Project()
    master = _track("master", "/tmp/master.wav")
    p.add_track(master)
    others = [_track(n, f"/tmp/{n}.wav") for n in non_master_names]
    for t in others:
        p.add_track(t)
    p.set_master(master.id)
    return p, master, others


# ---------------------------------------------------------------------------


def test_no_master_raises():
    p = Project()
    p.add_track(_track("a", "/tmp/a.wav"))
    with pytest.raises(InvalidProjectState):
        sync_all_to_master(
            p,
            path_resolver=lambda t: t.source_path,
            compute_fn=lambda m, x: (0.0, 1.0),
        )


def test_happy_path_writes_offsets_and_confidences():
    p, master, (a, b) = _project_with_master("a", "b")

    results = {
        "/tmp/a.wav": (0.25, 0.9),
        "/tmp/b.wav": (-0.5, 0.7),
    }

    def compute_fn(master_path: str, track_path: str) -> tuple[float, float]:
        assert master_path == "/tmp/master.wav"
        return results[track_path]

    sync_all_to_master(
        p,
        path_resolver=lambda t: t.source_path,
        compute_fn=compute_fn,
    )

    assert a.offset_to_master == 0.25
    assert a.confidence == 0.9
    assert b.offset_to_master == -0.5
    assert b.confidence == 0.7
    # Master untouched.
    assert master.offset_to_master == 0.0
    assert master.confidence is None


def test_master_is_skipped_by_compute_fn():
    p, master, (a,) = _project_with_master("a")
    calls: list[tuple[str, str]] = []

    def compute_fn(m: str, x: str) -> tuple[float, float]:
        calls.append((m, x))
        return (0.1, 0.8)

    sync_all_to_master(
        p,
        path_resolver=lambda t: t.source_path,
        compute_fn=compute_fn,
    )

    assert calls == [("/tmp/master.wav", "/tmp/a.wav")]


def test_progress_fires_once_per_non_master():
    p, master, others = _project_with_master("a", "b", "c")
    seen: list[str] = []

    sync_all_to_master(
        p,
        path_resolver=lambda t: t.source_path,
        compute_fn=lambda m, x: (0.0, 1.0),
        progress=lambda track: seen.append(track.display_name),
    )

    assert seen == ["a", "b", "c"]


def test_progress_sees_track_after_update():
    p, master, (a,) = _project_with_master("a")
    snapshots: list[tuple[float | None, float | None]] = []

    def progress(track: AudioTrack) -> None:
        snapshots.append((track.offset_to_master, track.confidence))

    sync_all_to_master(
        p,
        path_resolver=lambda t: t.source_path,
        compute_fn=lambda m, x: (1.5, 0.95),
        progress=progress,
    )

    assert snapshots == [(1.5, 0.95)]


def test_no_non_master_tracks_is_noop():
    p = Project()
    m = _track("master", "/tmp/m.wav")
    p.add_track(m)
    p.set_master(m.id)

    calls: list[tuple[str, str]] = []
    progress_calls: list[AudioTrack] = []

    sync_all_to_master(
        p,
        path_resolver=lambda t: t.source_path,
        compute_fn=lambda a, b: (calls.append((a, b)) or (0.0, 1.0)),
        progress=lambda t: progress_calls.append(t),
    )

    assert calls == []
    assert progress_calls == []
    assert m.offset_to_master == 0.0
    assert m.confidence is None


def test_path_resolver_called_per_track():
    p, master, (a, b) = _project_with_master("a", "b")
    resolved: list[str] = []

    def resolver(track: AudioTrack) -> str:
        resolved.append(track.display_name)
        return track.source_path

    sync_all_to_master(
        p,
        path_resolver=resolver,
        compute_fn=lambda m, x: (0.0, 1.0),
    )

    # Master resolved first, then each non-master once.
    assert resolved == ["master", "a", "b"]


def test_path_resolver_return_value_is_used():
    p, master, (a,) = _project_with_master("a")

    resolver_map = {
        master.id: "/cache/master-extracted.wav",
        a.id: "/cache/a-extracted.wav",
    }
    seen_paths: list[tuple[str, str]] = []

    def compute_fn(m: str, x: str) -> tuple[float, float]:
        seen_paths.append((m, x))
        return (0.0, 1.0)

    sync_all_to_master(
        p,
        path_resolver=lambda t: resolver_map[t.id],
        compute_fn=compute_fn,
    )

    assert seen_paths == [
        ("/cache/master-extracted.wav", "/cache/a-extracted.wav")
    ]


def test_default_compute_fn_is_compute_offset():
    from app.core import project_sync, sync_engine

    assert sync_all_to_master.__defaults__ is None  # kw-only default
    # Verify the default referenced in the signature is compute_offset.
    import inspect

    sig = inspect.signature(project_sync.sync_all_to_master)
    assert sig.parameters["compute_fn"].default is sync_engine.compute_offset
