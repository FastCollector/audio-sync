"""
Compute the time offset between two audio recordings via cross-correlation
of onset strength envelopes.

Using envelopes instead of raw samples makes the algorithm robust to
codec differences (e.g. iPhone AAC mic vs Zoom WAV line-in): both recordings
share the same transient events (speech starts, hand claps, instrument hits)
regardless of frequency response or compression.
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

    # Compute onset strength envelopes. These capture the temporal pattern of
    # energy bursts (transients) and are invariant to timbre, EQ, and codec.
    # hop_length=512 at 16kHz → ~32ms per frame, accurate enough for sync.
    hop = 512
    ref_env = librosa.onset.onset_strength(y=ref, sr=SAMPLE_RATE, hop_length=hop)
    ext_env = librosa.onset.onset_strength(y=ext, sr=SAMPLE_RATE, hop_length=hop)

    print(f"[sync] ref envelope: {len(ref_env)} frames")
    print(f"[sync] ext envelope: {len(ext_env)} frames")

    ref_env = _normalize(ref_env)
    ext_env = _normalize(ext_env)

    corr = correlate(ref_env, ext_env, mode="full", method="fft")

    n_ref = len(ref_env)
    n_ext = len(ext_env)
    lags = np.arange(-(n_ext - 1), n_ref)

    # Normalize by overlap length to make the score comparable across lags.
    overlap = np.maximum(
        np.minimum(n_ref, lags + n_ext) - np.maximum(0, lags),
        1,
    )
    corr_per_frame = corr / overlap

    peak_idx = np.argmax(np.abs(corr_per_frame))
    # Convert frame lag → seconds
    offset_seconds = float(lags[peak_idx] * hop / SAMPLE_RATE)
    confidence = float(min(1.0, abs(corr_per_frame[peak_idx])))

    print(f"[sync] peak correlation: {abs(corr_per_frame[peak_idx]):.4f}")
    print(f"[sync] confidence:       {confidence:.4f}")
    print(f"[sync] offset:           {offset_seconds:+.4f}s")

    return offset_seconds, confidence


def _normalize(a: np.ndarray) -> np.ndarray:
    a = a - a.mean()
    std = a.std()
    if std > 1e-8:
        a = a / std
    return a
