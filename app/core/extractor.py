"""Audio extraction helpers backed by FFmpeg."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_DURATION_PATTERN = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _parse_duration_seconds(stderr: str) -> float:
    match = _DURATION_PATTERN.search(stderr)
    if not match:
        raise ValueError("Could not parse duration from ffmpeg stderr")
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def extract_audio(input_path: str | Path, output_wav_path: str | Path, sample_rate: int = 48000) -> float:
    """Extract mono PCM WAV and return media duration in seconds."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        str(output_wav_path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return _parse_duration_seconds(result.stderr)
