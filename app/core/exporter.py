"""
Export a video with all original audio tracks plus an additional synced
external audio track (audio B).

Video stream:          copied (no re-encode).
Original audio tracks: copied from video input.
Audio B:               encoded to AAC, positioned at the computed offset.
"""

import re
import subprocess

import imageio_ffmpeg


def export(
    video_path: str,
    audio_b_path: str,
    offset: float,
    output_path: str,
    trim_audio_end: float | None = None,
    trim_video_end: float | None = None,
) -> None:
    """
    Mux video + all original audio tracks + audio B (at offset) into output.

    Args:
        offset:        Seconds audio B starts relative to video start.
                       Positive → audio B delayed; negative → audio B trimmed at start.
        trim_audio_end: If set, keep only this many seconds of audio B content
                        (measured from the start of the audio B file, before offset).
        trim_video_end: If set, trim the output to this duration in seconds.
    """
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    n_orig_audio = _count_audio_streams(ffmpeg, video_path)
    audio_filter = _build_audio_b_filter(offset, trim_audio_end)

    # Copy video; copy each original audio stream; encode audio B as AAC.
    codec_args = ["-c:v", "copy"]
    for i in range(n_orig_audio):
        codec_args += [f"-c:a:{i}", "copy"]
    codec_args += [f"-c:a:{n_orig_audio}", "aac"]

    duration_args = ["-t", str(trim_video_end)] if trim_video_end is not None else []

    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-i", audio_b_path,
        "-filter_complex", audio_filter,
        "-map", "0:v",
        "-map", "0:a",      # all original audio tracks
        "-map", "[b_out]",  # audio B (filtered)
        *codec_args,
        *duration_args,
        output_path,
    ]

    subprocess.run(cmd, check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_audio_b_filter(offset: float, trim_audio_end: float | None) -> str:
    """
    Return a filter_complex string that positions audio B at `offset` seconds.

    Positive offset → adelay (add silence at start of audio B).
    Negative offset → atrim (skip the portion before video start).
    trim_audio_end  → further limit how much of audio B is used.
    """
    if offset >= 0:
        delay_ms = int(round(offset * 1000))
        if trim_audio_end is not None:
            # Trim audio B to the needed duration first, then delay.
            return (
                f"[1:a]atrim=duration={trim_audio_end:.6f},"
                f"adelay={delay_ms}:all=1[b_out]"
            )
        return f"[1:a]adelay={delay_ms}:all=1[b_out]"
    else:
        # audio B started before the video; skip the pre-video portion.
        start = abs(offset)
        if trim_audio_end is not None:
            end = start + trim_audio_end
            return (
                f"[1:a]atrim=start={start:.6f}:end={end:.6f},"
                f"asetpts=PTS-STARTPTS[b_out]"
            )
        return f"[1:a]atrim=start={start:.6f},asetpts=PTS-STARTPTS[b_out]"


def _count_audio_streams(ffmpeg: str, video_path: str) -> int:
    result = subprocess.run([ffmpeg, "-i", video_path], capture_output=True, text=True)
    return len(re.findall(r"Stream #0:\d+.*?Audio:", result.stderr))
