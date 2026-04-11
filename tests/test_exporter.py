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
