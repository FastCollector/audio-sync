"""
Export a video with all original audio tracks plus an additional synced
external audio track (audio B).

Video stream:          copied (no re-encode).
Original audio tracks: volume-adjusted and re-encoded to AAC if volume != 1.0,
                       otherwise copied.
Audio B:               encoded to AAC, positioned at the computed offset.
"""

import re
from pathlib import Path

from app.core.ffmpeg_utils import get_ffmpeg_executable, probe_media, run_ffmpeg


def export(
    video_path: str,
    audio_b_path: str,
    offset: float,
    output_path: str,
    trim_audio_end: float | None = None,
    trim_video_start: float | None = None,
    trim_video_end: float | None = None,
    video_audio_volume: float = 1.0,
    audio_b_volume: float = 1.0,
) -> None:
    """
    Mux video + all original audio tracks + audio B (at offset) into output.

    Args:
        offset:              Seconds audio B starts relative to video start.
        trim_audio_end:      Keep only this many seconds of audio B content.
        trim_video_start:    Output starts at this position in the video (seconds).
        trim_video_end:      Output ends at this position in the video (seconds, absolute).
        video_audio_volume:  Volume multiplier for original video audio (0.0–1.0).
        audio_b_volume:      Volume multiplier for audio B (0.0–1.0).
    """
    ffmpeg = get_ffmpeg_executable()
    audio_indices = _find_audio_stream_indices(ffmpeg, video_path)
    n_orig_audio = len(audio_indices)

    # When the video is trimmed from trim_start, adjust audio B offset so it
    # still aligns with the original content: adjusted = offset - trim_start
    effective_offset = offset - (trim_video_start or 0.0)

    # Build filter_complex: handles audio B position + volumes.
    # Original audio streams go through volume filter → [va0_out], [va1_out], …
    # Audio B goes through position + volume filter → [b_out]
    filter_parts = []
    va_labels = []
    for i, stream_idx in enumerate(audio_indices):
        label = f"[va{i}_out]"
        filter_parts.append(f"[0:{stream_idx}]volume={video_audio_volume:.6f}{label}")
        va_labels.append(label)

    filter_parts.append(
        _build_audio_b_filter(effective_offset, trim_audio_end, audio_b_volume)
    )
    filter_complex = ";".join(filter_parts)

    out = _ensure_extension(output_path)
    output_ext = Path(out).suffix.lower()
    # MP4-family containers cannot hold PCM or many compressed codecs — re-encode to AAC.
    # Other containers (MKV etc.) can stream-copy most codecs.
    # Note: when original audio goes through the volume filter it must be re-encoded
    # regardless; force_aac ensures correctness for MP4 even if the filter is later removed.
    force_aac_for_original_audio = output_ext in {".mp4", ".m4v", ".ismv"}

    codec_args = ["-c:v", "copy"]
    for i in range(n_orig_audio):
        codec_args += [f"-c:a:{i}", "aac" if force_aac_for_original_audio else "copy"]
    codec_args += [f"-c:a:{n_orig_audio}", "aac"]

    # Input-side -ss for trim start: FFmpeg seeks to the nearest keyframe, so
    # stream-copied video always begins on a clean keyframe (no black first frames).
    # Trade-off: start may be up to one GOP earlier than the exact trim point.
    # End time uses -t (duration) because input-side seek resets output timestamps.
    # When there is no trim start, output-side -to is exact and has no keyframe issue.
    input_seek_args: list[str] = []
    output_trim_args: list[str] = []
    if trim_video_start is not None:
        input_seek_args = ["-ss", str(trim_video_start)]
        if trim_video_end is not None:
            output_trim_args = ["-t", str(trim_video_end - trim_video_start)]
    elif trim_video_end is not None:
        output_trim_args = ["-to", str(trim_video_end)]

    cmd = [
        ffmpeg, "-y",
        *input_seek_args,
        "-i", video_path,
        "-i", audio_b_path,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        *[arg for label in va_labels for arg in ("-map", label)],
        "-map", "[b_out]",
        *codec_args,
        *output_trim_args,
        "-avoid_negative_ts", "make_zero",
        out,
    ]

    run_ffmpeg(cmd)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_audio_b_filter(offset: float, trim_audio_end: float | None, volume: float) -> str:
    """
    Return the filter chain for audio B: position at offset + optional trim + volume.
    """
    vol = f"volume={volume:.6f},"

    if offset >= 0:
        delay_ms = int(round(offset * 1000))
        if trim_audio_end is not None:
            return (
                f"[1:a]{vol}atrim=duration={trim_audio_end:.6f},"
                f"adelay={delay_ms}:all=1[b_out]"
            )
        return f"[1:a]{vol}adelay={delay_ms}:all=1[b_out]"
    else:
        start = abs(offset)
        if trim_audio_end is not None:
            end = start + trim_audio_end
            return (
                f"[1:a]{vol}atrim=start={start:.6f}:end={end:.6f},"
                f"asetpts=PTS-STARTPTS[b_out]"
            )
        return f"[1:a]{vol}atrim=start={start:.6f},asetpts=PTS-STARTPTS[b_out]"


def _ensure_extension(path: str) -> str:
    p = Path(path)
    return path if p.suffix else path + ".mp4"


def _find_audio_stream_indices(ffmpeg: str, video_path: str) -> list[int]:
    """Return stream indices of decodable audio streams (excludes 'Audio: none' e.g. APAC)."""
    result = probe_media([ffmpeg, "-i", video_path])
    return [
        int(m.group(1))
        for m in re.finditer(r"Stream #0:(\d+).*?Audio: (?!none)", result.stderr)
    ]
