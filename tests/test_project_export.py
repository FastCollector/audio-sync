"""
Stage 3 tests for app.core.project_export.

`build_export_cmd` is pure — no I/O. The parity test monkeypatches the
legacy `exporter.export`'s external dependencies to capture its argv and
checks byte-for-byte equivalence (modulo the audio-B label rename from
`[b_out]` to `[ex0_out]`).
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
from app.core.project_export import build_export_cmd


# ---------------------------------------------------------------------------
# Fixtures


def _make_project(
    *,
    externals: list[tuple[str, float]] | None = None,
    trim_start: float | None = None,
    trim_end: float | None = None,
    video_path: str = "video.mp4",
) -> tuple[Project, AudioTrack, list[AudioTrack]]:
    p = Project()
    p.video_asset = VideoAsset(
        path=video_path, duration_seconds=60.0, has_embedded_audio=True
    )
    emb = AudioTrack(
        display_name="embedded",
        source_kind=SourceKind.VIDEO_EMBEDDED,
        source_path=video_path,
        duration_seconds=60.0,
    )
    p.add_track(emb)
    p.link_embedded_audio(emb.id)

    ext_tracks: list[AudioTrack] = []
    for name, _ in (externals or []):
        t = AudioTrack(
            display_name=name,
            source_kind=SourceKind.EXTERNAL,
            source_path=f"{name}.wav",
            duration_seconds=60.0,
        )
        p.add_track(t)
        ext_tracks.append(t)

    p.set_master(emb.id)
    for t, (_, offset) in zip(ext_tracks, (externals or [])):
        t.offset_to_master = offset

    p.project_trim_start = trim_start
    p.project_trim_end = trim_end
    return p, emb, ext_tracks


# ---------------------------------------------------------------------------
# Scope violations raise


def test_no_video_asset_raises():
    p = Project()
    with pytest.raises(InvalidProjectState):
        build_export_cmd(p, "out.mp4", volumes={}, video_audio_indices=[1], ffmpeg="ffmpeg")


def test_missing_embedded_raises():
    p = Project()
    p.video_asset = VideoAsset(path="v.mp4", duration_seconds=10.0, has_embedded_audio=True)
    with pytest.raises(InvalidProjectState):
        build_export_cmd(p, "out.mp4", volumes={}, video_audio_indices=[1], ffmpeg="ffmpeg")


def test_second_embedded_track_raises():
    p, emb, _ = _make_project()
    # Add an unlinked VIDEO_EMBEDDED track — not allowed by Stage 3 scope.
    stray = AudioTrack(
        display_name="stray",
        source_kind=SourceKind.VIDEO_EMBEDDED,
        source_path="other.mp4",
        duration_seconds=1.0,
    )
    p.add_track(stray)
    with pytest.raises(InvalidProjectState):
        build_export_cmd(p, "out.mp4", volumes={}, video_audio_indices=[1], ffmpeg="ffmpeg")


# ---------------------------------------------------------------------------
# Happy-path structure


def test_embedded_only_no_externals():
    p, emb, _ = _make_project()
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    assert cmd[:4] == ["ffmpeg", "-y", "-i", "video.mp4"]
    assert "-c:v" in cmd and cmd[cmd.index("-c:v") + 1] == "copy"
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert filt == "[0:1]volume=1.000000[va0_out]"
    # Only video-audio mapped — no external mapping.
    mapped = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-map"]
    assert mapped == ["0:v", "[va0_out]"]


def test_positive_offset_uses_adelay():
    p, emb, (a,) = _make_project(externals=[("a", 0.25)])
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0, a.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert "adelay=250:all=1" in filt
    assert "atrim" not in filt


def test_negative_offset_uses_atrim():
    p, emb, (a,) = _make_project(externals=[("a", -0.4)])
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0, a.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert "atrim=start=0.400000" in filt
    assert "adelay" not in filt


def test_trim_start_and_end_produce_ss_and_t():
    p, emb, _ = _make_project(trim_start=1.0, trim_end=5.0)
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    # -ss precedes -i, -t follows output side.
    assert cmd.index("-ss") < cmd.index("-i")
    assert cmd[cmd.index("-ss") + 1] == "1.0"
    assert cmd[cmd.index("-t") + 1] == "4.0"
    assert "-to" not in cmd


def test_trim_end_only_produces_to():
    p, emb, _ = _make_project(trim_end=5.0)
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    assert "-ss" not in cmd
    assert cmd[cmd.index("-to") + 1] == "5.0"


def test_trim_shifts_external_offset():
    # external offset = 0.25, trim_start = 0.10 → effective adelay = 150ms.
    p, emb, (a,) = _make_project(externals=[("a", 0.25)], trim_start=0.10)
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0, a.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert "adelay=150:all=1" in filt


def test_mp4_forces_aac_for_video_audio():
    p, emb, _ = _make_project()
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    assert cmd[cmd.index("-c:a:0") + 1] == "aac"


def test_mkv_copies_video_audio():
    p, emb, _ = _make_project()
    cmd = build_export_cmd(
        p, "out.mkv",
        volumes={emb.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    assert cmd[cmd.index("-c:a:0") + 1] == "copy"


def test_multiple_externals_numbered_in_order():
    p, emb, (a, b) = _make_project(externals=[("a", 0.1), ("b", -0.2)])
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0, a.id: 1.0, b.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert "[ex0_out]" in filt
    assert "[ex1_out]" in filt
    mapped = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-map"]
    assert mapped == ["0:v", "[va0_out]", "[ex0_out]", "[ex1_out]"]
    # -c:a:0 = video audio, -c:a:1 = external a, -c:a:2 = external b.
    assert cmd[cmd.index("-c:a:1") + 1] == "aac"
    assert cmd[cmd.index("-c:a:2") + 1] == "aac"


def test_multiple_video_audio_streams():
    p, emb, (a,) = _make_project(externals=[("a", 0.0)])
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 0.5, a.id: 1.0},
        video_audio_indices=[1, 2],
        ffmpeg="ffmpeg",
    )
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:1]volume=0.500000[va0_out]" in filt
    assert "[0:2]volume=0.500000[va1_out]" in filt
    mapped = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-map"]
    assert mapped == ["0:v", "[va0_out]", "[va1_out]", "[ex0_out]"]


def test_volumes_applied_per_track():
    p, emb, (a,) = _make_project(externals=[("a", 0.0)])
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 0.2, a.id: 0.8},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert "volume=0.200000" in filt
    assert "volume=0.800000" in filt


def test_external_input_order_matches_track_order():
    p, emb, (a, b) = _make_project(externals=[("a", 0.0), ("b", 0.0)])
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0, a.id: 1.0, b.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    # Inputs: video, a.wav, b.wav in that order.
    i_indices = [i for i, x in enumerate(cmd) if x == "-i"]
    assert [cmd[i + 1] for i in i_indices] == ["video.mp4", "a.wav", "b.wav"]


# ---------------------------------------------------------------------------
# Parity with legacy single-external exporter


def test_parity_with_legacy_single_external(monkeypatch):
    """
    For the 1-video + 1-external compatibility scenario, the new builder
    must produce argv byte-for-byte identical to `exporter.export`, modulo
    the label rename [b_out] -> [ex0_out].
    """
    captured: list[list[str]] = []
    monkeypatch.setattr(
        "app.core.exporter.run_ffmpeg",
        lambda cmd: captured.append(list(cmd)),
    )
    monkeypatch.setattr(
        "app.core.exporter.get_ffmpeg_executable",
        lambda: "ffmpeg",
    )
    monkeypatch.setattr(
        "app.core.exporter._find_audio_stream_indices",
        lambda _ffmpeg, _path: [1],
    )

    from app.core.exporter import export

    export(
        "video.mp4",
        "ext.wav",
        offset=0.25,
        output_path="out.mp4",
        trim_video_start=1.5,
        trim_video_end=10.0,
        video_audio_volume=0.8,
        audio_b_volume=1.2,
    )
    legacy_cmd = captured[0]

    # Equivalent Project build.
    p, emb, (a,) = _make_project(
        externals=[("ext", 0.25)],
        trim_start=1.5,
        trim_end=10.0,
    )
    # Legacy uses "ext.wav" as raw path; _make_project uses "ext.wav" too.
    assert a.source_path == "ext.wav"

    new_cmd = build_export_cmd(
        p,
        "out.mp4",
        volumes={emb.id: 0.8, a.id: 1.2},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )

    # Normalize label: legacy's [b_out] corresponds to Stage 3's [ex0_out].
    legacy_normalized = [arg.replace("b_out", "ex0_out") for arg in legacy_cmd]
    assert new_cmd == legacy_normalized


def test_parity_negative_offset(monkeypatch):
    captured: list[list[str]] = []
    monkeypatch.setattr(
        "app.core.exporter.run_ffmpeg",
        lambda cmd: captured.append(list(cmd)),
    )
    monkeypatch.setattr(
        "app.core.exporter.get_ffmpeg_executable",
        lambda: "ffmpeg",
    )
    monkeypatch.setattr(
        "app.core.exporter._find_audio_stream_indices",
        lambda _ffmpeg, _path: [1],
    )

    from app.core.exporter import export

    export(
        "video.mp4",
        "ext.wav",
        offset=-0.4,
        output_path="out.mp4",
        video_audio_volume=1.0,
        audio_b_volume=1.0,
    )
    legacy_cmd = captured[0]

    p, emb, (a,) = _make_project(externals=[("ext", -0.4)])
    new_cmd = build_export_cmd(
        p,
        "out.mp4",
        volumes={emb.id: 1.0, a.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )

    legacy_normalized = [arg.replace("b_out", "ex0_out") for arg in legacy_cmd]
    assert new_cmd == legacy_normalized


def test_parity_mkv_output(monkeypatch):
    captured: list[list[str]] = []
    monkeypatch.setattr(
        "app.core.exporter.run_ffmpeg",
        lambda cmd: captured.append(list(cmd)),
    )
    monkeypatch.setattr(
        "app.core.exporter.get_ffmpeg_executable",
        lambda: "ffmpeg",
    )
    monkeypatch.setattr(
        "app.core.exporter._find_audio_stream_indices",
        lambda _ffmpeg, _path: [1],
    )

    from app.core.exporter import export

    export(
        "video.mp4",
        "ext.wav",
        offset=0.0,
        output_path="out.mkv",
    )
    legacy_cmd = captured[0]

    p, emb, (a,) = _make_project(externals=[("ext", 0.0)])
    new_cmd = build_export_cmd(
        p,
        "out.mkv",
        volumes={emb.id: 1.0, a.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )

    legacy_normalized = [arg.replace("b_out", "ex0_out") for arg in legacy_cmd]
    assert new_cmd == legacy_normalized


# ---------------------------------------------------------------------------
# Stage 6B: non-zero video_offset_to_master triggers re-encode path


def _make_reencode_project(
    *,
    video_offset: float,
    externals: list[tuple[str, float]] | None = None,
    trim_start: float | None = None,
    trim_end: float | None = None,
) -> tuple[Project, AudioTrack, list[AudioTrack]]:
    p, emb, exts = _make_project(
        externals=externals, trim_start=trim_start, trim_end=trim_end
    )
    emb.offset_to_master = video_offset
    return p, emb, exts


def test_positive_video_offset_uses_tpad():
    p, emb, _ = _make_reencode_project(video_offset=0.5)
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:v]tpad=start_duration=0.500000:start_mode=add:color=black[v_out]" in filt
    assert "trim=" not in filt.split(";")[0]


def test_negative_video_offset_uses_trim_setpts():
    p, emb, _ = _make_reencode_project(video_offset=-0.4)
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:v]trim=start=0.400000,setpts=PTS-STARTPTS[v_out]" in filt
    assert "tpad" not in filt


def test_reencode_uses_libx264():
    p, emb, _ = _make_reencode_project(video_offset=0.5)
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[cmd.index("-c:a:0") + 1] == "aac"


def test_reencode_maps_v_out_instead_of_0v():
    p, emb, _ = _make_reencode_project(video_offset=0.5)
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    mapped = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-map"]
    assert "0:v" not in mapped
    assert "[v_out]" in mapped


def test_reencode_no_input_side_ss():
    p, emb, _ = _make_reencode_project(video_offset=0.5, trim_start=1.0, trim_end=5.0)
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    i_idx = cmd.index("-i")
    assert "-ss" not in cmd[:i_idx]
    assert cmd[cmd.index("-t") + 1] == "4.0"


def test_reencode_trim_applied_after_shift():
    p, emb, _ = _make_reencode_project(video_offset=0.5, trim_start=1.0, trim_end=5.0)
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    filt = cmd[cmd.index("-filter_complex") + 1]
    video_chain = filt.split(";")[0]
    assert video_chain.startswith("[0:v]tpad=start_duration=0.500000")
    assert video_chain.endswith("[v_out]")
    assert video_chain.index("tpad") < video_chain.index("trim=start=1.000000")
    assert "trim=start=1.000000:end=5.000000" in video_chain
    assert "setpts=PTS-STARTPTS" in video_chain


def test_reencode_embedded_audio_shifted():
    p, emb, _ = _make_reencode_project(video_offset=0.5)
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:1]volume=1.000000,adelay=500:all=1[va0_out]" in filt


def test_reencode_embedded_audio_negative_offset_atrim():
    p, emb, _ = _make_reencode_project(video_offset=-0.4)
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:1]volume=1.000000,atrim=start=0.400000,asetpts=PTS-STARTPTS[va0_out]" in filt


def test_reencode_external_offset_math_unchanged():
    p, emb, (a,) = _make_reencode_project(
        video_offset=0.5,
        externals=[("a", 0.25)],
        trim_start=0.10,
    )
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0, a.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert "adelay=150:all=1" in filt


def test_zero_offset_path_unchanged_by_6b():
    p, emb, _ = _make_project()
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert "[v_out]" not in cmd
    assert "libx264" not in cmd


def test_master_external_with_synced_embedded_triggers_reencode():
    # Master is external and embedded has a computed offset → re-encode path.
    p, emb, (a,) = _make_project(externals=[("a", 0.0)])
    p.set_master(a.id)
    emb.offset_to_master = -0.3
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0, a.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:v]trim=start=0.300000,setpts=PTS-STARTPTS[v_out]" in filt
