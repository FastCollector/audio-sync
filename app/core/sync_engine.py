"""
Compute the time offset between two audio recordings.

Stage 1 (coarse): onset-strength envelope cross-correlation.
  Robust to codec/EQ differences; resolution ~32 ms (one hop at 16 kHz).

Stage 2 (refinement): GCC-PHAT on the raw waveform within ±50 ms of the
  coarse offset.  Phase-whitening makes it insensitive to spectral colour;
  resolution is one sample (0.0625 ms at 16 kHz).
"""

import numpy as np
import librosa
from scipy.signal import correlate

SAMPLE_RATE = 16000  # Hz — sufficient for transient-based sync detection
_REFINE_RADIUS = int(0.05 * SAMPLE_RATE)  # 800 samples = 50 ms


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
    ref, ref_sr = librosa.load(ref_audio_path, sr=SAMPLE_RATE, mono=True, res_type="scipy")
    ext, ext_sr = librosa.load(ext_audio_path, sr=SAMPLE_RATE, mono=True, res_type="scipy")

    print(f"[sync] ref audio:  {len(ref)} samples @ {ref_sr} Hz  ({len(ref)/ref_sr:.2f}s)")
    print(f"[sync] ext audio:  {len(ext)} samples @ {ext_sr} Hz  ({len(ext)/ext_sr:.2f}s)")

    # Stage 1 — coarse alignment via onset-strength envelope cross-correlation.
    # Envelopes capture transient timing and are invariant to timbre/EQ/codec.
    # hop_length=512 at 16 kHz → ~32 ms per frame.
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

    # Normalize by sqrt(n_ref * n_ext) to avoid inflating edge lags.
    norm_factor = float(np.sqrt(n_ref * n_ext))
    corr_norm = corr / norm_factor if norm_factor > 0 else corr

    abs_corr = np.abs(corr_norm)
    peak_idx = np.argmax(abs_corr)
    coarse_offset = float(lags[peak_idx] * hop / SAMPLE_RATE)

    # Confidence: peak-to-second-peak ratio.
    # Mask ±1 s around the main peak before finding the second peak.
    mask_radius = int(SAMPLE_RATE / hop)
    masked = abs_corr.copy()
    lo = max(0, peak_idx - mask_radius)
    hi = min(len(masked), peak_idx + mask_radius + 1)
    masked[lo:hi] = 0.0
    second_peak = float(masked.max()) if masked.max() > 0 else 1e-9
    peak_val = float(abs_corr[peak_idx])
    confidence = float(min(1.0, 1.0 - second_peak / peak_val)) if peak_val > 0 else 0.0

    print(f"[sync] coarse offset:  {coarse_offset:+.4f}s  confidence: {confidence:.4f}")

    # Stage 2 — GCC-PHAT refinement within ±50 ms of the coarse offset.
    refined_offset = _refine_gcc_phat(ref, ext, coarse_offset)

    print(f"[sync] refined offset: {refined_offset:+.4f}s  (delta: {(refined_offset - coarse_offset)*1000:+.1f} ms)")

    return refined_offset, confidence


def _refine_gcc_phat(ref: np.ndarray, ext: np.ndarray, coarse_offset_s: float) -> float:
    """
    Refine coarse_offset_s within ±50 ms using GCC-PHAT on raw waveforms.
    Returns coarse_offset_s unchanged if there is insufficient overlap.
    """
    coarse_samples = int(round(coarse_offset_s * SAMPLE_RATE))

    ref_start = max(0, coarse_samples)
    ext_start = max(0, -coarse_samples)

    overlap = min(len(ref) - ref_start, len(ext) - ext_start)
    if overlap <= 2 * _REFINE_RADIUS:
        return coarse_offset_s

    # 2-second anchor window from the centre of the overlap.
    seg_len = min(2 * SAMPLE_RATE, overlap - 2 * _REFINE_RADIUS)
    if seg_len <= 0:
        return coarse_offset_s

    mid = overlap // 2
    r_seg = ref[ref_start + mid - seg_len // 2 : ref_start + mid + seg_len // 2]
    e_seg = ext[ext_start + mid - seg_len // 2 : ext_start + mid + seg_len // 2]

    if len(r_seg) == 0 or len(e_seg) == 0:
        return coarse_offset_s

    # GCC-PHAT: whiten the cross-spectrum then IFFT.
    n_fft = 1
    while n_fft < len(r_seg) + len(e_seg) - 1:
        n_fft <<= 1

    cross = np.fft.rfft(r_seg, n=n_fft) * np.conj(np.fft.rfft(e_seg, n=n_fft))
    denom = np.abs(cross)
    denom[denom < 1e-10] = 1e-10
    gcc = np.fft.irfft(cross / denom, n=n_fft)

    # Search within ±_REFINE_RADIUS samples of lag 0.
    # In the IFFT output: positive lags at [1.._REFINE_RADIUS],
    # negative lags wrap to [n_fft-_REFINE_RADIUS..n_fft-1].
    pos_vals = gcc[: _REFINE_RADIUS + 1]
    neg_vals = gcc[n_fft - _REFINE_RADIUS : n_fft]
    search_vals = np.concatenate([pos_vals, neg_vals])
    search_lags = np.concatenate(
        [np.arange(0, _REFINE_RADIUS + 1), np.arange(-_REFINE_RADIUS, 0)]
    )

    fine_lag = int(search_lags[np.argmax(search_vals)])
    return coarse_offset_s + fine_lag / SAMPLE_RATE


def _normalize(a: np.ndarray) -> np.ndarray:
    a = a - a.mean()
    std = a.std()
    if std > 1e-8:
        a = a / std
    return a
