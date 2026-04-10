import random

from app.core.sync_engine import estimate_sync_offset

FPS = 24
FRAME_SEC = 1 / FPS


def _noise(seed: int, n: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(0, 1) for _ in range(n)]


def test_correlated_signals_high_confidence_and_accurate_offset():
    sample_rate = 8_000
    shift_samples = int(round(0.25 * sample_rate))
    base = _noise(7, sample_rate)
    shifted = [0.0] * shift_samples + base

    result = estimate_sync_offset(base, shifted, sample_rate)

    assert result.confidence >= 0.8
    assert abs(result.offset_seconds - 0.25) <= FRAME_SEC


def test_unrelated_noise_low_confidence():
    sample_rate = 8_000
    a = _noise(42, sample_rate)
    b = _noise(43, sample_rate)

    result = estimate_sync_offset(a, b, sample_rate)

    assert result.confidence < 0.5
