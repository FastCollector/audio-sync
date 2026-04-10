"""Length comparison logic."""

from __future__ import annotations

from enum import Enum

TOLERANCE_SECONDS = 0.5


class LengthState(str, Enum):
    ALIGNED = "ALIGNED"
    AUDIO_OVERFLOW = "AUDIO_OVERFLOW"
    VIDEO_OVERFLOW = "VIDEO_OVERFLOW"


def check_lengths(video_duration: float, audio_duration: float, tolerance: float = TOLERANCE_SECONDS) -> LengthState:
    delta = audio_duration - video_duration
    if abs(delta) <= tolerance:
        return LengthState.ALIGNED
    if delta > tolerance:
        return LengthState.AUDIO_OVERFLOW
    return LengthState.VIDEO_OVERFLOW
