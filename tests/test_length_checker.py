from app.core.length_checker import LengthState, TOLERANCE_SECONDS, check_lengths


def test_length_state_aligned_within_tolerance():
    assert check_lengths(10.0, 10.4) == LengthState.ALIGNED
    assert check_lengths(10.0, 9.6) == LengthState.ALIGNED
    assert TOLERANCE_SECONDS == 0.5


def test_length_state_audio_overflow_beyond_tolerance():
    assert check_lengths(10.0, 10.51) == LengthState.AUDIO_OVERFLOW


def test_length_state_video_overflow_beyond_tolerance():
    assert check_lengths(10.0, 9.49) == LengthState.VIDEO_OVERFLOW
