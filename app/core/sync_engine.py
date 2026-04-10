"""Signal synchronization core."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class SyncResult:
    offset_seconds: float
    confidence: float


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def estimate_sync_offset(signal_a: list[float], signal_b: list[float], sample_rate: int) -> SyncResult:
    """Estimate relative offset where positive means B lags A."""
    if not signal_a or not signal_b:
        raise ValueError("Signals must be non-empty")

    a_mean = _mean(signal_a)
    b_mean = _mean(signal_b)
    a = [x - a_mean for x in signal_a]
    b = [x - b_mean for x in signal_b]

    best_lag = 0
    best_corr = 0.0

    min_lag = -len(a) + 1
    max_lag = len(b) - 1
    for lag in range(min_lag, max_lag + 1):
        corr = 0.0
        for i, ai in enumerate(a):
            j = i + lag
            if 0 <= j < len(b):
                corr += ai * b[j]
        if abs(corr) > abs(best_corr):
            best_corr = corr
            best_lag = lag

    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(x * x for x in b))
    norm = norm_a * norm_b
    confidence = 0.0 if norm == 0 else min(1.0, abs(best_corr) / norm)

    return SyncResult(offset_seconds=best_lag / sample_rate, confidence=confidence)
