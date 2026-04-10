"""Extract audio from a video file using the bundled FFmpeg binary."""

import re
import subprocess
import tempfile
import os

import imageio_ffmpeg


def extract_audio(video_path: str) -> tuple[str, float]:
    """
    Extract mono 16 kHz audio from a video file to a temporary WAV.

    Returns:
        (wav_path, video_duration_seconds)
        Caller is responsible for deleting the temp WAV file.
    """
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    video_duration = _get_duration(ffmpeg, video_path)

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()

    subprocess.run(
        [
            ffmpeg, "-y", "-i", video_path,
            "-vn",          # no video
            "-ac", "1",     # mono
            "-ar", "16000", # 16 kHz (sufficient for sync detection)
            tmp.name,
        ],
        check=True,
        capture_output=True,
    )

    return tmp.name, video_duration


def _get_duration(ffmpeg: str, path: str) -> float:
    """Parse media duration from ffmpeg -i stderr output."""
    result = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", result.stderr)
    if not match:
        raise ValueError(f"Could not determine duration of: {path}")
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)
