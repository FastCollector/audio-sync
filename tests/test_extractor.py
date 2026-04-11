"""
Tests for app.core.extractor.

Patches at the ffmpeg_utils layer (where the actual subprocess calls live),
not at extractor.subprocess.run / extractor.imageio_ffmpeg (which no longer
exist as direct dependencies after the ffmpeg_utils refactor).
"""

import os
import subprocess

from app.core.extractor import extract_audio, _get_duration


def _fake_probe(stderr: str):
    """Return a probe_media replacement that always returns the given stderr."""
    return lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=stderr)


def _fake_run(calls: list, stderr: str = ""):
    """Return a run_ffmpeg replacement that records calls."""
    def inner(cmd, **kw):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr=stderr)
    return inner


def test_get_duration_parses_standard_format(monkeypatch):
    stderr = "  Duration: 00:00:10.50, start: 0.000, bitrate: 768 kb/s"
    monkeypatch.setattr("app.core.extractor.probe_media", _fake_probe(stderr))
    monkeypatch.setattr("app.core.extractor.get_ffmpeg_executable", lambda: "ffmpeg")
    assert _get_duration("ffmpeg", "v.mp4") == 10.5


def test_get_duration_parses_hours_minutes_seconds(monkeypatch):
    stderr = "ffmpeg version n6\n  Duration: 01:02:03.25, start: 0.000000, bitrate: 768 kb/s\n"
    monkeypatch.setattr("app.core.extractor.probe_media", _fake_probe(stderr))
    monkeypatch.setattr("app.core.extractor.get_ffmpeg_executable", lambda: "ffmpeg")
    assert _get_duration("ffmpeg", "v.mov") == 3723.25


def test_extract_audio_uses_mono_16khz_flags_and_returns_duration(monkeypatch):
    duration_stderr = "  Duration: 00:00:05.00, start: 0.000000"
    calls = []

    monkeypatch.setattr("app.core.extractor.get_ffmpeg_executable", lambda: "ffmpeg")
    monkeypatch.setattr("app.core.extractor.probe_media", _fake_probe(duration_stderr))
    monkeypatch.setattr("app.core.extractor.run_ffmpeg", _fake_run(calls))

    wav_path, duration = extract_audio("video.mp4")
    try:
        assert len(calls) == 1
        cmd = calls[0]
        assert "-vn" in cmd
        assert "-ac" in cmd
        assert "1" in cmd
        assert "16000" in cmd
        assert duration == 5.0
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)
