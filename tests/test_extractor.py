"""
Tests for app.core.extractor.

Our API (differs from original PR):
    extract_audio(video_path: str) -> tuple[str, float]
        manages temp file internally; uses imageio_ffmpeg, not bare "ffmpeg"

    _get_duration(ffmpeg: str, path: str) -> float
        pure stderr parser, testable directly
"""

import os
import subprocess

from app.core.extractor import extract_audio, _get_duration


def test_get_duration_parses_standard_format(monkeypatch):
    stderr = "  Duration: 00:00:10.50, start: 0.000, bitrate: 768 kb/s"
    monkeypatch.setattr(
        "app.core.ffmpeg_utils.subprocess.run",
        lambda *a, **kw: subprocess.CompletedProcess([], 0, stdout="", stderr=stderr),
    )
    assert _get_duration("ffmpeg", "v.mp4") == 10.5


def test_get_duration_parses_hours_minutes_seconds(monkeypatch):
    stderr = "ffmpeg version n6\n  Duration: 01:02:03.25, start: 0.000000, bitrate: 768 kb/s\n"
    monkeypatch.setattr(
        "app.core.ffmpeg_utils.subprocess.run",
        lambda *a, **kw: subprocess.CompletedProcess([], 0, stdout="", stderr=stderr),
    )
    assert _get_duration("ffmpeg", "v.mov") == 3723.25


def test_extract_audio_uses_mono_16khz_flags_and_returns_duration(monkeypatch):
    stderr = "  Duration: 00:00:05.00, start: 0.000000"
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr=stderr)

    monkeypatch.setattr("app.core.ffmpeg_utils.imageio_ffmpeg.get_ffmpeg_exe", lambda: "ffmpeg")
    monkeypatch.setattr("app.core.ffmpeg_utils.subprocess.run", fake_run)

    wav_path, duration = extract_audio("video.mp4")
    try:
        # The extraction call contains -ar; the duration probe call does not.
        extract_cmd = next(c for c in calls if "-ar" in c)
        assert "-vn" in extract_cmd
        assert "-ac" in extract_cmd
        assert "1" in extract_cmd      # mono
        assert "16000" in extract_cmd  # 16 kHz
        assert duration == 5.0
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)
