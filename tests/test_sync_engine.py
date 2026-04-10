"""
Tests for app.core.sync_engine.

Our API (differs from original PR):
    compute_offset(ref_audio_path: str, ext_audio_path: str) -> tuple[float, float]
        takes file paths, returns (offset_seconds, confidence)

The PR called estimate_sync_offset(list, list, sr) -> SyncResult.
We test via real WAV files written to tmp_path.

Signal model for positive-offset test:
    ref = silence(shift) + base   (video: silent at start, then content)
    ext = base                    (audio B: content starts immediately)
    → audio B content aligns at ref position `shift`, so offset = +0.25 s
"""

import numpy as np
import soundfile as sf

from app.core.sync_engine import compute_offset, SAMPLE_RATE

FPS = 24
FRAME_SEC = 1 / FPS


def test_correlated_signals_high_confidence_and_accurate_offset(tmp_path):
    rng = np.random.default_rng(7)
    # 3 s of base audio — long enough that the 0.25 s padding is a small fraction.
    base = rng.standard_normal(3 * SAMPLE_RATE).astype(np.float32)
    shift_samples = int(round(0.25 * SAMPLE_RATE))

    ref = np.pad(base, (shift_samples, 0))  # silence then content
    ext = base                               # content immediately

    sf.write(str(tmp_path / "ref.wav"), ref, SAMPLE_RATE)
    sf.write(str(tmp_path / "ext.wav"), ext, SAMPLE_RATE)

    offset, confidence = compute_offset(
        str(tmp_path / "ref.wav"),
        str(tmp_path / "ext.wav"),
    )

    assert confidence >= 0.8
    assert abs(offset - 0.25) <= FRAME_SEC


def test_unrelated_noise_low_confidence(tmp_path):
    rng = np.random.default_rng(0)
    a = rng.standard_normal(SAMPLE_RATE).astype(np.float32)
    b = rng.standard_normal(SAMPLE_RATE).astype(np.float32)

    sf.write(str(tmp_path / "a.wav"), a, SAMPLE_RATE)
    sf.write(str(tmp_path / "b.wav"), b, SAMPLE_RATE)

    _, confidence = compute_offset(
        str(tmp_path / "a.wav"),
        str(tmp_path / "b.wav"),
    )

    assert confidence < 0.5
