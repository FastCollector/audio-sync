"""Extract audio from a video file using the bundled FFmpeg binary."""

from __future__ import annotations

import os
import re
import tempfile

from app.core.ffmpeg_utils import get_ffmpeg_executable, probe_media, run_ffmpeg


def extract_audio(video_path: str) -> tuple[str, float]:
    """
    Extract mono 16 kHz audio from a video file to a temporary WAV.

    Returns:
        (wav_path, video_duration_seconds)
        Caller is responsible for deleting the temp WAV file.
    """
    ffmpeg = get_ffmpeg_executable()
    video_duration = _get_duration(ffmpeg, video_path)

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()

    run_ffmpeg(
        [
            ffmpeg, "-y", "-i", video_path,
            "-vn",          # no video
            "-ac", "1",     # mono
            "-ar", "16000", # 16 kHz (sufficient for sync detection)
            tmp.name,
        ],
    )

    return tmp.name, video_duration


def _get_duration(ffmpeg: str, path: str) -> float:
    """Parse media duration from ffmpeg -i stderr output."""
    result = probe_media([ffmpeg, "-i", path])

    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", result.stderr)
    if not match:
        raise ValueError(f"Could not determine duration of: {path}")
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)
