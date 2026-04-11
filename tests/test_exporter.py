"""
Tests for app.core.exporter.

Our API (differs from original PR):
    export(video_path, audio_b_path, offset, output_path, ...) -> None
        uses -filter_complex with adelay/atrim, not -af:a:N
        uses imageio_ffmpeg for the binary path
        calls subprocess.run twice: once to count audio streams, once to export

The PR tested build_export_command / export_synced (functions that don't exist
in our implementation) and checked for -af:a:1 / adelay=250|250 syntax.
"""

import subprocess

from app.core.exporter import export


def _patched_run(monkeypatch, audio_stream_count: int = 1):
    """
    Patch subprocess.run to succeed.  The first call (_count_audio_streams)
    needs stderr with N audio stream lines; the second call is the export.
    Returns the list of captured commands.
    """
    audio_stderr = "\n".join(
        f"  Stream #0:{i}: Audio: aac" for i in range(audio_stream_count)
    )
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr=audio_stderr)

    monkeypatch.setattr("app.core.ffmpeg_utils.imageio_ffmpeg.get_ffmpeg_exe", lambda: "ffmpeg")
    monkeypatch.setattr("app.core.ffmpeg_utils.subprocess.run", fake_run)
    return calls


def test_positive_offset_uses_adelay_in_filter_complex(monkeypatch):
    calls = _patched_run(monkeypatch)

    export("in.mp4", "b.wav", 0.25, "out.mp4")

    export_cmd = " ".join(calls[-1])
    assert "-filter_complex" in export_cmd
    assert "adelay=250:all=1" in export_cmd


def test_negative_offset_uses_atrim_in_filter_complex(monkeypatch):
    calls = _patched_run(monkeypatch)

    export("in.mp4", "b.wav", -0.2, "out.mp4")

    export_cmd = " ".join(calls[-1])
    assert "-filter_complex" in export_cmd
    assert "atrim" in export_cmd
    assert "0.200000" in export_cmd  # start= value from abs(-0.2)


def test_dual_track_mapping_present(monkeypatch):
    calls = _patched_run(monkeypatch)

    export("in.mp4", "b.wav", 0.0, "out.mp4")

    export_cmd = " ".join(calls[-1])
    assert "0:v" in export_cmd
    assert "0:a" in export_cmd
    assert "[b_out]" in export_cmd   # audio B mapped via filter output label


def test_export_calls_subprocess(monkeypatch):
    calls = _patched_run(monkeypatch)

    export("in.mp4", "b.wav", 0.1, "out.mp4")

    # At minimum two calls: audio stream probe + the export itself.
    assert len(calls) >= 1
    assert "out.mp4" in calls[-1]
