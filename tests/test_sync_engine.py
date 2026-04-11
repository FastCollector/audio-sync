"""
Tests for app.core.sync_engine.

Our API:
    compute_offset(ref_audio_path: str, ext_audio_path: str) -> tuple[float, float]
        takes file paths, returns (offset_seconds, confidence)

Signal model:
    The sync engine uses onset-strength envelopes (librosa.onset.onset_strength),
    not raw sample correlation.  White noise has no transients so its onset
    envelope is flat — useless for this algorithm.  We use sparse unit impulses
    instead: each impulse produces a sharp onset event that the envelope detects
    cleanly.

    Correlated test:
        base = sparse impulses over 3 s
        ref  = silence(0.25 s) + base
        ext  = base
        → audio B content starts at ref position +0.25 s → offset = +0.25 s

    Unrelated test:
        a = impulses at one set of positions
        b = impulses at a completely different set of positions
        → onset envelopes have nothing in common → all correlation lags similar
          → low confidence
"""

import numpy as np
import soundfile as sf

from app.core.sync_engine import compute_offset, SAMPLE_RATE

FPS = 24
FRAME_SEC = 1 / FPS


def _impulse_signal(duration_s: float, n_impulses: int, rng: np.random.Generator) -> np.ndarray:
    """Sparse unit impulses at random positions — clear onset events, no periodic structure."""
    n = int(duration_s * SAMPLE_RATE)
    sig = np.zeros(n, dtype=np.float32)
    # Random placement with a minimum gap to keep impulses resolvable.
    min_gap = SAMPLE_RATE // 20  # 50 ms
    placed: list[int] = []
    attempts = 0
    while len(placed) < n_impulses and attempts < 100_000:
        pos = int(rng.integers(0, n))
        if all(abs(pos - p) >= min_gap for p in placed):
            placed.append(pos)
            sig[pos] = 1.0
        attempts += 1
    return sig


def test_correlated_signals_high_confidence_and_accurate_offset(tmp_path):
    rng = np.random.default_rng(7)
    base = _impulse_signal(5.0, 20, rng)
    shift_samples = int(round(0.25 * SAMPLE_RATE))

    ref = np.pad(base, (shift_samples, 0))  # silence then impulses
    ext = base                               # impulses start immediately

    sf.write(str(tmp_path / "ref.wav"), ref, SAMPLE_RATE)
    sf.write(str(tmp_path / "ext.wav"), ext, SAMPLE_RATE)

    offset, confidence = compute_offset(
        str(tmp_path / "ref.wav"),
        str(tmp_path / "ext.wav"),
    )

    assert confidence >= 0.8
    assert abs(offset - 0.25) <= FRAME_SEC


def test_unrelated_noise_low_confidence(tmp_path):
    # Two independent impulse patterns over 5 s — long enough that the ±1 s
    # mask window doesn't consume all secondary peaks in the correlation output.
    rng_a = np.random.default_rng(1)
    rng_b = np.random.default_rng(2)
    a = _impulse_signal(5.0, 15, rng_a)
    b = _impulse_signal(5.0, 15, rng_b)

    sf.write(str(tmp_path / "a.wav"), a, SAMPLE_RATE)
    sf.write(str(tmp_path / "b.wav"), b, SAMPLE_RATE)

    _, confidence = compute_offset(
        str(tmp_path / "a.wav"),
        str(tmp_path / "b.wav"),
    )

    assert confidence < 0.5
