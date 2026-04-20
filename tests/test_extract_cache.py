"""
Stage 4 tests for app.core.extract_cache.

`extract_audio` is monkeypatched — no real ffmpeg invocation. We verify:
    - cache destination path shape (root/<project_id>/<track_id>.wav)
    - extraction happens on miss, skipped on hit
    - track.extracted_wav_path gets populated
    - resolver() satisfies Stage-2's path_resolver contract
    - sweep_stale deletes old dirs, keeps fresh ones
    - integration with sync_all_to_master
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest

from app.core.extract_cache import ExtractCache
from app.core.project import (
    AudioTrack,
    Project,
    SourceKind,
    VideoAsset,
)
from app.core.project_sync import sync_all_to_master


# ---------------------------------------------------------------------------
# Fixtures


@pytest.fixture
def fake_extract(monkeypatch):
    """Replace extract_audio with a stub that writes a known tempfile."""
    calls: list[str] = []

    def _fake(source_path: str) -> tuple[str, float]:
        calls.append(source_path)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.write(f"fake:{source_path}".encode())
        tmp.close()
        return tmp.name, 10.0

    monkeypatch.setattr("app.core.extract_cache.extract_audio", _fake)
    return calls


def _project_with_tracks(video_path: str = "video.mp4") -> tuple[Project, AudioTrack, AudioTrack]:
    p = Project()
    p.video_asset = VideoAsset(
        path=video_path, duration_seconds=10.0, has_embedded_audio=True
    )
    emb = AudioTrack(
        display_name="embedded",
        source_kind=SourceKind.VIDEO_EMBEDDED,
        source_path=video_path,
        duration_seconds=10.0,
    )
    ext = AudioTrack(
        display_name="ext",
        source_kind=SourceKind.EXTERNAL,
        source_path="ext.wav",
        duration_seconds=10.0,
    )
    p.add_track(emb)
    p.add_track(ext)
    p.link_embedded_audio(emb.id)
    p.set_master(emb.id)
    return p, emb, ext


# ---------------------------------------------------------------------------
# path_for


def test_path_for_uses_project_id_and_track_id(tmp_path):
    cache = ExtractCache(tmp_path)
    p, emb, ext = _project_with_tracks()
    assert cache.path_for(p, emb) == tmp_path / p.id / f"{emb.id}.wav"
    assert cache.path_for(p, ext) == tmp_path / p.id / f"{ext.id}.wav"


# ---------------------------------------------------------------------------
# ensure_extracted — miss & hit


def test_ensure_extracted_miss_triggers_extraction(tmp_path, fake_extract):
    cache = ExtractCache(tmp_path)
    p, emb, _ = _project_with_tracks()

    result = cache.ensure_extracted(p, emb)

    expected = tmp_path / p.id / f"{emb.id}.wav"
    assert result == str(expected)
    assert expected.exists()
    assert emb.extracted_wav_path == str(expected)
    assert fake_extract == [emb.source_path]


def test_ensure_extracted_hit_skips_extraction(tmp_path, fake_extract):
    cache = ExtractCache(tmp_path)
    p, emb, _ = _project_with_tracks()

    first = cache.ensure_extracted(p, emb)
    second = cache.ensure_extracted(p, emb)

    assert first == second
    assert len(fake_extract) == 1  # only one real extraction


def test_ensure_extracted_miss_when_file_removed(tmp_path, fake_extract):
    """Even if track.extracted_wav_path is set, re-extract when the file is gone."""
    cache = ExtractCache(tmp_path)
    p, emb, _ = _project_with_tracks()

    cache.ensure_extracted(p, emb)
    Path(emb.extracted_wav_path).unlink()

    cache.ensure_extracted(p, emb)
    assert len(fake_extract) == 2
    assert Path(emb.extracted_wav_path).exists()


def test_ensure_extracted_ignores_stale_extracted_wav_path(tmp_path, fake_extract):
    """A path from a previous cache root must not count as a hit."""
    cache = ExtractCache(tmp_path)
    p, emb, _ = _project_with_tracks()
    emb.extracted_wav_path = str(tmp_path / "somewhere_else.wav")
    # Even if we pre-create that file:
    Path(emb.extracted_wav_path).write_text("old")

    cache.ensure_extracted(p, emb)
    expected = tmp_path / p.id / f"{emb.id}.wav"
    assert emb.extracted_wav_path == str(expected)
    assert expected.exists()
    assert len(fake_extract) == 1


def test_ensure_extracted_embedded_and_external_same_cache_dir(tmp_path, fake_extract):
    cache = ExtractCache(tmp_path)
    p, emb, ext = _project_with_tracks()

    emb_path = Path(cache.ensure_extracted(p, emb))
    ext_path = Path(cache.ensure_extracted(p, ext))

    assert emb_path.parent == ext_path.parent == tmp_path / p.id
    assert emb_path != ext_path


# ---------------------------------------------------------------------------
# resolver


def test_resolver_satisfies_stage2_contract(tmp_path, fake_extract):
    cache = ExtractCache(tmp_path)
    p, emb, ext = _project_with_tracks()
    resolve = cache.resolver(p)

    # Resolver takes a track, returns a str.
    result = resolve(ext)
    assert isinstance(result, str)
    assert result == str(tmp_path / p.id / f"{ext.id}.wav")


def test_resolver_bound_to_project(tmp_path, fake_extract):
    cache = ExtractCache(tmp_path)
    p1, emb1, _ = _project_with_tracks()
    p2 = Project()
    p2.video_asset = VideoAsset(path="other.mp4", duration_seconds=5.0, has_embedded_audio=True)
    emb2 = AudioTrack(
        display_name="emb2",
        source_kind=SourceKind.VIDEO_EMBEDDED,
        source_path="other.mp4",
        duration_seconds=5.0,
    )
    p2.add_track(emb2)
    p2.link_embedded_audio(emb2.id)
    p2.set_master(emb2.id)

    r1 = cache.resolver(p1)
    r2 = cache.resolver(p2)

    assert r1(emb1).startswith(str(tmp_path / p1.id))
    assert r2(emb2).startswith(str(tmp_path / p2.id))


# ---------------------------------------------------------------------------
# sweep_stale


def test_sweep_stale_deletes_old_dirs(tmp_path):
    cache = ExtractCache(tmp_path)
    old = tmp_path / "old_project"
    fresh = tmp_path / "fresh_project"
    old.mkdir()
    fresh.mkdir()
    (old / "x.wav").write_text("x")
    (fresh / "y.wav").write_text("y")

    # Backdate 'old' by 48 hours.
    past = time.time() - 48 * 3600
    os.utime(old, (past, past))

    deleted = cache.sweep_stale(max_age_hours=24.0)

    assert str(old) in deleted
    assert str(fresh) not in deleted
    assert not old.exists()
    assert fresh.exists()


def test_sweep_stale_missing_root_returns_empty(tmp_path):
    cache = ExtractCache(tmp_path / "does_not_exist")
    assert cache.sweep_stale() == []


def test_sweep_stale_ignores_files_at_root(tmp_path):
    cache = ExtractCache(tmp_path)
    stray_file = tmp_path / "stray.wav"
    stray_file.write_text("x")
    past = time.time() - 48 * 3600
    os.utime(stray_file, (past, past))

    deleted = cache.sweep_stale(max_age_hours=24.0)
    assert deleted == []
    assert stray_file.exists()


# ---------------------------------------------------------------------------
# Integration with Stage 2


def test_integration_with_sync_all_to_master(tmp_path, fake_extract):
    cache = ExtractCache(tmp_path)
    p, emb, ext = _project_with_tracks()

    seen_paths: list[tuple[str, str]] = []

    def fake_compute(master_path: str, track_path: str) -> tuple[float, float]:
        seen_paths.append((master_path, track_path))
        return (0.25, 0.9)

    sync_all_to_master(
        p,
        path_resolver=cache.resolver(p),
        compute_fn=fake_compute,
    )

    # compute_fn gets the cache paths (not source_path).
    cache_dir = tmp_path / p.id
    assert seen_paths == [
        (str(cache_dir / f"{emb.id}.wav"), str(cache_dir / f"{ext.id}.wav"))
    ]
    # Both files exist on disk.
    assert (cache_dir / f"{emb.id}.wav").exists()
    assert (cache_dir / f"{ext.id}.wav").exists()
    # Stage 2 wrote offset/confidence on the external track.
    assert ext.offset_to_master == 0.25
    assert ext.confidence == 0.9
    # Master untouched.
    assert emb.offset_to_master == 0.0
    assert emb.confidence is None
    # Each track extracted exactly once.
    assert len(fake_extract) == 2
