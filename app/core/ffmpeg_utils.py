"""Helpers for invoking FFmpeg with user-friendly error reporting."""

from __future__ import annotations

import subprocess

import imageio_ffmpeg


class FFmpegError(RuntimeError):
    """Raised when FFmpeg is missing or a media operation fails."""


_CORRUPT_MEDIA_HINTS = (
    "invalid data found",
    "moov atom not found",
    "error while decoding",
    "failed to read frame",
)


def get_ffmpeg_executable() -> str:
    """Return the imageio-ffmpeg binary path, with a clear error if unavailable."""
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - depends on environment
        raise FFmpegError(
            "FFmpeg is unavailable. Reinstall imageio-ffmpeg or use the packaged app build."
        ) from exc


def run_ffmpeg(cmd: list[str], *, text: bool = False) -> subprocess.CompletedProcess:
    """Run an FFmpeg command and convert low-level failures into readable errors."""
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=text)
    except FileNotFoundError as exc:
        raise FFmpegError(
            "FFmpeg executable was not found. Reinstall imageio-ffmpeg or rebuild the app package."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = _stderr_text(exc)
        lower_stderr = stderr.lower()
        if any(token in lower_stderr for token in _CORRUPT_MEDIA_HINTS):
            raise FFmpegError(
                "The selected media file appears to be corrupt or unsupported. "
                "Please choose a different file."
            ) from exc

        details = stderr.splitlines()[-1].strip() if stderr.strip() else "Unknown FFmpeg error"
        raise FFmpegError(f"FFmpeg failed: {details}") from exc


def probe_media(cmd: list[str]) -> subprocess.CompletedProcess:
    """
    Run ffmpeg probing commands (like `ffmpeg -i`) that often return non-zero.

    We still parse stderr for corrupt/missing-file diagnostics.
    """
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise FFmpegError(
            "FFmpeg executable was not found. Reinstall imageio-ffmpeg or rebuild the app package."
        ) from exc

    lower_stderr = (result.stderr or "").lower()
    if any(token in lower_stderr for token in _CORRUPT_MEDIA_HINTS):
        raise FFmpegError(
            "The selected media file appears to be corrupt or unsupported. "
            "Please choose a different file."
        )

    return result


def _stderr_text(exc: subprocess.CalledProcessError) -> str:
    if isinstance(exc.stderr, bytes):
        return exc.stderr.decode("utf-8", errors="ignore")
    return exc.stderr or ""
