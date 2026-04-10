"""
Compute the time offset between two audio recordings via cross-correlation.

Both recordings are assumed to contain the same source audio (e.g. a music
performance captured simultaneously by a camera mic and an external recorder).
"""

import numpy as np
import librosa
from scipy.signal import correlate

SAMPLE_RATE = 16000  # Hz — sufficient for transient-based sync detection


def compute_offset(ref_audio_path: str, ext_audio_path: str) -> tuple[float, float]:
    """
    Compute time offset between a reference audio (extracted from video) and
    an external audio recording.

    Returns:
        (offset_seconds, confidence)

        offset_seconds:
            Positive  → audio B starts this many seconds AFTER video start.
            Negative  → audio B started this many seconds BEFORE video start.

        confidence:
            0–1 scale.  > 0.8 = strong match.  < 0.5 = likely wrong/unrelated.
    """
    ref, ref_sr = librosa.load(ref_audio_path, sr=SAMPLE_RATE, mono=True)
    ext, ext_sr = librosa.load(ext_audio_path, sr=SAMPLE_RATE, mono=True)

    print(f"[sync] ref audio:  {len(ref)} samples @ {ref_sr} Hz  ({len(ref)/ref_sr:.2f}s)")
    print(f"[sync] ext audio:  {len(ext)} samples @ {ext_sr} Hz  ({len(ext)/ext_sr:.2f}s)")

    # Normalize to zero-mean, unit variance so amplitude differences don't
    # affect the correlation magnitude.
    ref = _normalize(ref)
    ext = _normalize(ext)

    corr = correlate(ref, ext, mode="full", method="fft")

    n_ref = len(ref)
    n_ext = len(ext)
    lags = np.arange(-(n_ext - 1), n_ref)

    # Number of overlapping samples at each lag — used to normalize the
    # correlation into a per-sample correlation coefficient (≈ Pearson r).
    overlap = np.maximum(
        np.minimum(n_ref, lags + n_ext) - np.maximum(0, lags),
        1,
    )

    corr_per_sample = corr / overlap

    peak_idx = np.argmax(np.abs(corr_per_sample))
    offset_seconds = float(lags[peak_idx] / SAMPLE_RATE)
    confidence = float(min(1.0, abs(corr_per_sample[peak_idx])))

    print(f"[sync] peak correlation value: {abs(corr_per_sample[peak_idx]):.4f}")
    print(f"[sync] confidence:             {confidence:.4f}")
    print(f"[sync] offset:                 {offset_seconds:+.4f}s")

    return offset_seconds, confidence


def _normalize(audio: np.ndarray) -> np.ndarray:
    audio = audio - audio.mean()
    std = audio.std()
    if std > 1e-8:
        audio = audio / std
    return audio
