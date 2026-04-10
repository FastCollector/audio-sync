import subprocess
from unittest.mock import Mock

from app.core.extractor import extract_audio


def test_extract_audio_calls_ffmpeg_with_expected_args(monkeypatch, tmp_path):
    output = tmp_path / "out.wav"
    mocked = Mock(return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="Duration: 00:00:10.50"))
    monkeypatch.setattr("app.core.extractor.subprocess.run", mocked)

    duration = extract_audio("input.mp4", output, sample_rate=44100)

    assert duration == 10.5
    mocked.assert_called_once()
    cmd = mocked.call_args.args[0]
    assert cmd == [
        "ffmpeg",
        "-y",
        "-i",
        "input.mp4",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "44100",
        "-c:a",
        "pcm_s16le",
        str(output),
    ]


def test_extract_audio_parses_duration_from_stderr(monkeypatch, tmp_path):
    output = tmp_path / "out.wav"
    stderr = """ffmpeg version n6\n  Duration: 01:02:03.25, start: 0.000000, bitrate: 768 kb/s\n"""
    monkeypatch.setattr(
        "app.core.extractor.subprocess.run",
        Mock(return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=stderr)),
    )

    duration = extract_audio("input.mov", output)

    assert duration == 3723.25
