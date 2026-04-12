"""
Tests for app.core.exporter.

Patches at the ffmpeg_utils layer (get_ffmpeg_executable, probe_media,
run_ffmpeg) — the only FFmpeg entry points after the refactor.
"""

import subprocess

from app.core.exporter import export


def _patch_ffmpeg(monkeypatch, audio_stream_count: int = 1):
    """
    Patch ffmpeg_utils helpers used by exporter.
    probe_media returns stderr describing N decodable audio streams.
    run_ffmpeg records all calls and succeeds.
    Returns the recorded run_ffmpeg call list.
    """
    audio_stderr = "\n".join(
        f"  Stream #0:{i}: Audio: aac" for i in range(audio_stream_count)
    )
    calls = []

    monkeypatch.setattr("app.core.exporter.get_ffmpeg_executable", lambda: "ffmpeg")
    monkeypatch.setattr(
        "app.core.exporter.probe_media",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=audio_stderr),
    )

    def fake_run_ffmpeg(cmd, **kw):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("app.core.exporter.run_ffmpeg", fake_run_ffmpeg)
    return calls


def test_positive_offset_uses_adelay_in_filter_complex(monkeypatch):
    calls = _patch_ffmpeg(monkeypatch)
    export("in.mp4", "b.wav", 0.25, "out.mp4")
    export_cmd = " ".join(calls[-1])
    assert "-filter_complex" in export_cmd
    assert "adelay=250:all=1" in export_cmd


def test_negative_offset_uses_atrim_in_filter_complex(monkeypatch):
    calls = _patch_ffmpeg(monkeypatch)
    export("in.mp4", "b.wav", -0.2, "out.mp4")
    export_cmd = " ".join(calls[-1])
    assert "-filter_complex" in export_cmd
    assert "atrim" in export_cmd
    assert "0.200000" in export_cmd


def test_dual_track_mapping_present(monkeypatch):
    calls = _patch_ffmpeg(monkeypatch)
    export("in.mp4", "b.wav", 0.0, "out.mp4")
    export_cmd = " ".join(calls[-1])
    assert "0:v" in export_cmd
    assert "0:a" in export_cmd
    assert "[b_out]" in export_cmd


def test_export_calls_run_ffmpeg(monkeypatch):
    calls = _patch_ffmpeg(monkeypatch)
    export("in.mp4", "b.wav", 0.1, "out.mp4")
    assert len(calls) >= 1
    assert "out.mp4" in calls[-1]


def test_output_path_without_extension_gets_mp4(monkeypatch):
    calls = _patch_ffmpeg(monkeypatch)
    export("in.mp4", "b.wav", 0.0, "out_no_ext")
    assert calls[-1][-1] == "out_no_ext.mp4"


def test_mp4_output_reencodes_original_audio_to_aac(monkeypatch):
    calls = _patch_ffmpeg(monkeypatch, audio_stream_count=2)
    export("in.mov", "b.wav", 0.0, "out.mp4")
    cmd = calls[-1]
    assert ["-c:a:0", "aac"] == cmd[cmd.index("-c:a:0"): cmd.index("-c:a:0") + 2]
    assert ["-c:a:1", "aac"] == cmd[cmd.index("-c:a:1"): cmd.index("-c:a:1") + 2]


def test_non_mp4_output_copies_original_audio(monkeypatch):
    calls = _patch_ffmpeg(monkeypatch, audio_stream_count=1)
    export("in.mov", "b.wav", 0.0, "out.mkv")
    cmd = calls[-1]
    assert ["-c:a:0", "copy"] == cmd[cmd.index("-c:a:0"): cmd.index("-c:a:0") + 2]


def test_positive_offset_with_trim_start_uses_effective_offset_delay(monkeypatch):
    calls = _patch_ffmpeg(monkeypatch)
    export(
        "in.mp4",
        "b.wav",
        0.50,
        "out.mp4",
        trim_video_start=0.20,
    )
    export_cmd = " ".join(calls[-1])

    # effective_offset = 0.50 - 0.20 = +0.30 seconds
    assert "adelay=300:all=1" in export_cmd
    assert ["-ss", "0.2"] == calls[-1][calls[-1].index("-ss"): calls[-1].index("-ss") + 2]


def test_negative_offset_with_trim_start_uses_effective_offset_atrim(monkeypatch):
    calls = _patch_ffmpeg(monkeypatch)
    export(
        "in.mp4",
        "b.wav",
        -0.10,
        "out.mp4",
        trim_video_start=0.20,
    )
    export_cmd = " ".join(calls[-1])

    # effective_offset = -0.10 - 0.20 = -0.30 seconds
    assert "atrim=start=0.300000" in export_cmd
    assert "asetpts=PTS-STARTPTS" in export_cmd


def test_trim_video_end_adds_to_arg_without_changing_audio_offset(monkeypatch):
    calls = _patch_ffmpeg(monkeypatch)
    export(
        "in.mp4",
        "b.wav",
        0.40,
        "out.mp4",
        trim_video_end=5.0,
    )
    cmd = calls[-1]
    export_cmd = " ".join(cmd)

    # No trim start → effective_offset remains +0.40 seconds
    assert "adelay=400:all=1" in export_cmd
    assert ["-to", "5.0"] == cmd[cmd.index("-to"): cmd.index("-to") + 2]


def test_negative_effective_offset_with_trim_audio_end_trims_correct_segment(monkeypatch):
    calls = _patch_ffmpeg(monkeypatch)
    export(
        "in.mp4",
        "b.wav",
        -0.10,
        "out.mp4",
        trim_video_start=0.20,
        trim_audio_end=2.50,
    )
    export_cmd = " ".join(calls[-1])

    # effective_offset = -0.30, so atrim starts at 0.30 and ends at 2.80
    assert "atrim=start=0.300000:end=2.800000" in export_cmd
    assert "asetpts=PTS-STARTPTS" in export_cmd
