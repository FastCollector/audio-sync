"""Final export ffmpeg orchestration."""

from __future__ import annotations

import subprocess
from pathlib import Path


def build_export_command(video_with_audio_a: str | Path, audio_b: str | Path, output_path: str | Path, offset_seconds: float) -> list[str]:
    """Build ffmpeg command for dual-track output.

    Positive offset means audio B is delayed.
    Negative offset means prepend silence to audio A.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_with_audio_a),
        "-i",
        str(audio_b),
    ]

    delay_ms = int(round(abs(offset_seconds) * 1000))
    if delay_ms > 0:
        if offset_seconds >= 0:
            cmd += ["-af:a:1", f"adelay={delay_ms}|{delay_ms}"]
        else:
            cmd += ["-af:a:0", f"adelay={delay_ms}|{delay_ms}"]

    cmd += ["-map", "0:v", "-map", "0:a", "-map", "1:a", "-c:v", "copy", str(output_path)]
    return cmd


def export_synced(video_with_audio_a: str | Path, audio_b: str | Path, output_path: str | Path, offset_seconds: float) -> list[str]:
    cmd = build_export_command(video_with_audio_a, audio_b, output_path, offset_seconds)
    subprocess.run(cmd, check=True)
    return cmd
