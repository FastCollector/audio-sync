"""Detect and classify length mismatches between video and external audio."""

from dataclasses import dataclass
from enum import Enum

# Differences smaller than this are treated as aligned (handles rounding /
# encoder padding that adds a fraction of a second).
TOLERANCE_SECONDS = 0.5


class MismatchType(Enum):
    ALIGNED = "aligned"
    AUDIO_OVERFLOW = "audio_overflow"  # audio B extends past video end
    VIDEO_OVERFLOW = "video_overflow"  # video extends past aligned audio B end


@dataclass
class LengthCheckResult:
    mismatch_type: MismatchType
    overflow_seconds: float  # how many seconds of overflow (0 when ALIGNED)


def check_lengths(
    video_duration: float,
    audio_b_duration: float,
    offset: float,
) -> LengthCheckResult:
    """
    Determine whether the external audio fits within the video after applying
    the computed offset.

    offset > 0: audio B content starts `offset` seconds into the video.
    offset < 0: audio B content started `abs(offset)` seconds before video.

    In both cases, audio B ends at (offset + audio_b_duration) seconds
    relative to the video start.
    """
    audio_b_end = offset + audio_b_duration

    if audio_b_end > video_duration + TOLERANCE_SECONDS:
        return LengthCheckResult(MismatchType.AUDIO_OVERFLOW, audio_b_end - video_duration)

    if audio_b_end < video_duration - TOLERANCE_SECONDS:
        return LengthCheckResult(MismatchType.VIDEO_OVERFLOW, video_duration - audio_b_end)

    return LengthCheckResult(MismatchType.ALIGNED, 0.0)
