"""
Stage 1 tests for app.core.project data model.

Scope: pure data + invariants. No I/O, no sync behaviour.
"""

from __future__ import annotations

import pytest

from app.core.project import (
    AudioTrack,
    InvalidProjectState,
    Project,
    SourceKind,
    VideoAsset,
)


def _make_track(
    *,
    name: str = "track",
    kind: SourceKind = SourceKind.EXTERNAL,
    path: str = "/tmp/a.wav",
    duration: float = 10.0,
) -> AudioTrack:
    return AudioTrack(
        display_name=name,
        source_kind=kind,
        source_path=path,
        duration_seconds=duration,
    )


# ---------------------------------------------------------------------------
# AudioTrack construction


def test_audio_track_constructs_with_defaults():
    t = _make_track()
    assert t.display_name == "track"
    assert t.source_kind is SourceKind.EXTERNAL
    assert t.source_path == "/tmp/a.wav"
    assert t.duration_seconds == 10.0
    assert t.offset_to_master is None
    assert t.confidence is None
    assert t.extracted_wav_path is None
    assert isinstance(t.id, str) and len(t.id) > 0


def test_audio_track_ids_are_unique():
    a = _make_track()
    b = _make_track()
    assert a.id != b.id


# ---------------------------------------------------------------------------
# is_master derived from master_track_id


def test_is_master_derived_from_project():
    p = Project()
    t1 = _make_track(name="one")
    t2 = _make_track(name="two", path="/tmp/b.wav")
    p.add_track(t1)
    p.add_track(t2)
    assert p.is_master(t1) is False
    assert p.is_master(t2) is False

    p.set_master(t1.id)
    assert p.is_master(t1) is True
    assert p.is_master(t2) is False


# ---------------------------------------------------------------------------
# set_master zeros master's offset and clears others


def test_set_master_zeros_master_clears_others():
    p = Project()
    a = _make_track(name="a")
    b = _make_track(name="b", path="/tmp/b.wav")
    c = _make_track(name="c", path="/tmp/c.wav")
    for t in (a, b, c):
        p.add_track(t)

    # Pre-populate offsets/confidence on all tracks
    for t in (a, b, c):
        t.offset_to_master = 1.23
        t.confidence = 0.9

    p.set_master(b.id)

    assert b.offset_to_master == 0.0
    assert b.confidence is None
    assert a.offset_to_master is None and a.confidence is None
    assert c.offset_to_master is None and c.confidence is None


def test_set_master_unknown_raises():
    p = Project()
    p.add_track(_make_track())
    with pytest.raises(InvalidProjectState):
        p.set_master("nope")


# ---------------------------------------------------------------------------
# video_offset_to_master derivation


def test_video_offset_to_master_zero_when_no_video():
    p = Project()
    assert p.video_offset_to_master == 0.0


def test_video_offset_to_master_zero_when_no_embedded_link():
    p = Project()
    p.video_asset = VideoAsset(
        path="/tmp/v.mp4",
        duration_seconds=30.0,
        has_embedded_audio=False,
    )
    assert p.video_offset_to_master == 0.0


def test_video_offset_to_master_zero_when_embedded_has_no_offset():
    p = Project()
    p.video_asset = VideoAsset(
        path="/tmp/v.mp4",
        duration_seconds=30.0,
        has_embedded_audio=True,
    )
    emb = _make_track(
        name="embedded",
        kind=SourceKind.VIDEO_EMBEDDED,
        path="/tmp/v.mp4",
    )
    p.add_track(emb)
    p.link_embedded_audio(emb.id)
    assert emb.offset_to_master is None
    assert p.video_offset_to_master == 0.0


def test_video_offset_to_master_equals_embedded_offset():
    p = Project()
    p.video_asset = VideoAsset(
        path="/tmp/v.mp4",
        duration_seconds=30.0,
        has_embedded_audio=True,
    )
    emb = _make_track(
        name="embedded",
        kind=SourceKind.VIDEO_EMBEDDED,
        path="/tmp/v.mp4",
    )
    ext = _make_track(name="ext", path="/tmp/ext.wav")
    p.add_track(emb)
    p.add_track(ext)
    p.link_embedded_audio(emb.id)
    p.set_master(ext.id)
    emb.offset_to_master = -0.75
    assert p.video_offset_to_master == -0.75


# ---------------------------------------------------------------------------
# link_embedded_audio invariants


def test_link_embedded_requires_video_asset():
    p = Project()
    t = _make_track(kind=SourceKind.VIDEO_EMBEDDED, path="/tmp/v.mp4")
    p.add_track(t)
    with pytest.raises(InvalidProjectState):
        p.link_embedded_audio(t.id)


def test_link_embedded_rejects_external_kind():
    p = Project()
    p.video_asset = VideoAsset(
        path="/tmp/v.mp4",
        duration_seconds=10.0,
        has_embedded_audio=True,
    )
    t = _make_track(kind=SourceKind.EXTERNAL, path="/tmp/v.mp4")
    p.add_track(t)
    with pytest.raises(InvalidProjectState):
        p.link_embedded_audio(t.id)


def test_link_embedded_requires_matching_source_path():
    p = Project()
    p.video_asset = VideoAsset(
        path="/tmp/v.mp4",
        duration_seconds=10.0,
        has_embedded_audio=True,
    )
    t = _make_track(kind=SourceKind.VIDEO_EMBEDDED, path="/tmp/other.mp4")
    p.add_track(t)
    with pytest.raises(InvalidProjectState):
        p.link_embedded_audio(t.id)


def test_link_embedded_unknown_track_raises():
    p = Project()
    p.video_asset = VideoAsset(
        path="/tmp/v.mp4",
        duration_seconds=10.0,
        has_embedded_audio=True,
    )
    with pytest.raises(InvalidProjectState):
        p.link_embedded_audio("nope")


def test_link_embedded_success():
    p = Project()
    p.video_asset = VideoAsset(
        path="/tmp/v.mp4",
        duration_seconds=10.0,
        has_embedded_audio=True,
    )
    t = _make_track(kind=SourceKind.VIDEO_EMBEDDED, path="/tmp/v.mp4")
    p.add_track(t)
    p.link_embedded_audio(t.id)
    assert p.video_asset.embedded_audio_track_id == t.id
    assert p.embedded_audio_track() is t


# ---------------------------------------------------------------------------
# add_track / remove_track


def test_add_track_duplicate_id_raises():
    p = Project()
    t = _make_track()
    p.add_track(t)
    dup = AudioTrack(
        display_name="dup",
        source_kind=SourceKind.EXTERNAL,
        source_path="/tmp/x.wav",
        duration_seconds=1.0,
        id=t.id,
    )
    with pytest.raises(InvalidProjectState):
        p.add_track(dup)


def test_remove_unknown_track_raises():
    p = Project()
    with pytest.raises(InvalidProjectState):
        p.remove_track("nope")


def test_remove_master_clears_master_and_invalidates_offsets():
    p = Project()
    a = _make_track(name="a")
    b = _make_track(name="b", path="/tmp/b.wav")
    c = _make_track(name="c", path="/tmp/c.wav")
    for t in (a, b, c):
        p.add_track(t)
    p.set_master(a.id)
    b.offset_to_master = 0.5
    b.confidence = 0.9
    c.offset_to_master = -0.2
    c.confidence = 0.8

    p.remove_track(a.id)

    assert p.master_track_id is None
    assert p.master_track() is None
    assert b.offset_to_master is None and b.confidence is None
    assert c.offset_to_master is None and c.confidence is None


def test_remove_non_master_preserves_master():
    p = Project()
    a = _make_track(name="a")
    b = _make_track(name="b", path="/tmp/b.wav")
    p.add_track(a)
    p.add_track(b)
    p.set_master(a.id)
    b.offset_to_master = 0.5
    b.confidence = 0.9

    p.remove_track(b.id)

    assert p.master_track_id == a.id
    assert a.offset_to_master == 0.0


def test_remove_embedded_track_unlinks_from_video():
    p = Project()
    p.video_asset = VideoAsset(
        path="/tmp/v.mp4",
        duration_seconds=10.0,
        has_embedded_audio=True,
    )
    emb = _make_track(kind=SourceKind.VIDEO_EMBEDDED, path="/tmp/v.mp4")
    p.add_track(emb)
    p.link_embedded_audio(emb.id)

    p.remove_track(emb.id)

    assert p.video_asset.embedded_audio_track_id is None
    assert p.embedded_audio_track() is None


# ---------------------------------------------------------------------------
# Queries


def test_find_track_returns_none_for_unknown():
    p = Project()
    assert p.find_track("nope") is None


def test_master_track_none_when_unset():
    p = Project()
    p.add_track(_make_track())
    assert p.master_track() is None
