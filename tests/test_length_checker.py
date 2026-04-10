"""
Tests for app.core.length_checker.

Our API (differs from original PR):
    check_lengths(video_duration, audio_b_duration, offset) -> LengthCheckResult
        three args (offset is required); returns a dataclass with .mismatch_type

The PR used a two-arg check_lengths returning a LengthState enum directly.
We use offset=0.0 for the basic cases to reproduce equivalent arithmetic, and
add one test that verifies offset actually affects the classification.
"""

from app.core.length_checker import MismatchType, TOLERANCE_SECONDS, check_lengths


def test_aligned_within_tolerance():
    # audio_b_end = 0.0 + 10.4 = 10.4;  diff = 0.4 ≤ 0.5  → ALIGNED
    assert check_lengths(10.0, 10.4, 0.0).mismatch_type == MismatchType.ALIGNED
    # audio_b_end = 0.0 + 9.6 = 9.6;   diff = 0.4 ≤ 0.5  → ALIGNED
    assert check_lengths(10.0, 9.6, 0.0).mismatch_type == MismatchType.ALIGNED
    assert TOLERANCE_SECONDS == 0.5


def test_audio_overflow_beyond_tolerance():
    # audio_b_end = 0.0 + 10.51 = 10.51;  overflow = 0.51 > 0.5
    assert check_lengths(10.0, 10.51, 0.0).mismatch_type == MismatchType.AUDIO_OVERFLOW


def test_video_overflow_beyond_tolerance():
    # audio_b_end = 0.0 + 9.49 = 9.49;  video gap = 0.51 > 0.5
    assert check_lengths(10.0, 9.49, 0.0).mismatch_type == MismatchType.VIDEO_OVERFLOW


def test_offset_shifts_audio_b_end():
    # Without offset: 9.49 would be VIDEO_OVERFLOW.
    # With offset=+2.0: audio_b_end = 2.0 + 9.49 = 11.49 → AUDIO_OVERFLOW.
    assert check_lengths(10.0, 9.49, 2.0).mismatch_type == MismatchType.AUDIO_OVERFLOW
