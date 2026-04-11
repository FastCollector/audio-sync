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

    abs_corr = np.abs(corr_per_frame)
    peak_idx = np.argmax(abs_corr)
    coarse_lag_samples = int(lags[peak_idx] * hop)

    refined_lag_samples, raw_peak = _refine_lag_with_waveform(
        ref,
        ext,
        coarse_lag_samples,
        search_radius_samples=int(0.15 * SAMPLE_RATE),
    )

    # Convert sample lag → seconds
    offset_seconds = float(refined_lag_samples / SAMPLE_RATE)
    onset_confidence = _compute_confidence(abs_corr, peak_idx)
    raw_confidence = float(np.clip((raw_peak - 0.1) / 0.6, 0.0, 1.0))
    confidence = float(np.clip(0.35 * onset_confidence + 0.65 * raw_confidence, 0.0, 1.0))

    print(f"[sync] peak correlation: {abs_corr[peak_idx]:.4f}")
    print(f"[sync] raw correlation:  {raw_peak:.4f}")
    print(f"[sync] confidence:       {confidence:.4f}")
    print(f"[sync] offset:           {offset_seconds:+.4f}s")

    return offset_seconds, confidence


def _normalize(a: np.ndarray) -> np.ndarray:
    a = a - a.mean()
    std = a.std()
    if std > 1e-8:
        a = a / std
    return a


def _compute_confidence(abs_corr: np.ndarray, peak_idx: int) -> float:
    """
    Compute a robust confidence score from the correlation profile.

    We combine:
    - absolute peak strength
    - peak-to-next-best ratio (outside a small neighborhood)
    - robust z-score of peak versus global background (median/MAD)
    """
    peak = float(abs_corr[peak_idx])
    if len(abs_corr) <= 3:
        return float(np.clip(peak, 0.0, 1.0))

    neighborhood = 3
    mask = np.ones(len(abs_corr), dtype=bool)
    start = max(0, peak_idx - neighborhood)
    end = min(len(abs_corr), peak_idx + neighborhood + 1)
    mask[start:end] = False
    competitors = abs_corr[mask]
    next_best = float(np.max(competitors)) if competitors.size else 0.0
    peak_ratio = peak / (next_best + 1e-8)

    median = float(np.median(abs_corr))
    mad = float(np.median(np.abs(abs_corr - median))) + 1e-8
    robust_z = (peak - median) / (1.4826 * mad)

    peak_component = np.clip((peak - 0.2) / 0.8, 0.0, 1.0)
    ratio_component = np.clip((peak_ratio - 1.1) / 1.9, 0.0, 1.0)
    z_component = np.clip((robust_z - 2.0) / 8.0, 0.0, 1.0)

    score = 0.25 * peak_component + 0.35 * ratio_component + 0.40 * z_component
    return float(np.clip(score, 0.0, 1.0))


def _refine_lag_with_waveform(
    ref: np.ndarray,
    ext: np.ndarray,
    coarse_lag_samples: int,
    search_radius_samples: int,
) -> tuple[int, float]:
    """Refine lag using raw waveform cross-correlation around the onset-based estimate."""
    ref_n = _normalize(ref)
    ext_n = _normalize(ext)

    corr = correlate(ref_n, ext_n, mode="full", method="fft")
    n_ref = len(ref_n)
    n_ext = len(ext_n)
    lags = np.arange(-(n_ext - 1), n_ref)

    overlap = np.maximum(
        np.minimum(n_ref, lags + n_ext) - np.maximum(0, lags),
        1,
    )
    corr_per_sample = corr / overlap
    abs_corr = np.abs(corr_per_sample)

    mask = (lags >= coarse_lag_samples - search_radius_samples) & (
        lags <= coarse_lag_samples + search_radius_samples
    )
    if not np.any(mask):
        idx = int(np.argmax(abs_corr))
        return int(lags[idx]), float(abs_corr[idx])

    local_indices = np.where(mask)[0]
    best_local = int(local_indices[np.argmax(abs_corr[mask])])
    return int(lags[best_local]), float(abs_corr[best_local])
