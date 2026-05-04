"""Coarse candidate filter for offline batch processing.

The batch runner walks every M5 bar in the archive, but most bars are
boring chop. Sending every bar to the AI judge would burn the
subscription quota for no value. This filter answers a cheap, recall-
biased question:

    "Is there a swing-or-major pivot in the recent window, and either
    a meaningful range, a near-test of a recent extreme, or a fresh
    swing reversal? If yes, this is worth letting the AI look at."

False positives are fine — the AI will discard them. False negatives
are expensive (we miss training data forever) so the filter errs
generous.
"""

from __future__ import annotations

from dataclasses import dataclass

from fx_monitor.live.atr import atr
from fx_monitor.live.candle import Candle
from fx_monitor.live.pivots_v2 import detect_multi_scale_pivots


@dataclass
class CandidateDecision:
    is_candidate: bool
    reasons: list[str]


def is_candidate(
    candles_window: list[Candle],
    *,
    atr_period: int = 14,
    range_atr_threshold: float = 1.5,
    min_swing_pivots: int = 2,
) -> CandidateDecision:
    """Decide whether a window is worth handing to the AI judge."""
    reasons: list[str] = []
    if len(candles_window) < atr_period + 5:
        return CandidateDecision(False, ["window_too_short"])

    atr_val = atr(candles_window, period=atr_period)
    if atr_val <= 0:
        return CandidateDecision(False, ["atr_unavailable"])

    highs = [c.h for c in candles_window]
    lows = [c.l for c in candles_window]
    window_range = max(highs) - min(lows)

    pivots = detect_multi_scale_pivots(
        candles_window,
        atr_m5=atr_val,
        min_swing_atr_ratio=0.5,
    )
    swing_or_major = [p for p in pivots if p.scale in ("swing", "major")]

    has_strong_signal = False
    if len(swing_or_major) >= min_swing_pivots:
        reasons.append(f"swing_pivots={len(swing_or_major)}")
        has_strong_signal = True
    if window_range >= atr_val * range_atr_threshold:
        reasons.append(f"range_over_atr={window_range / atr_val:.2f}")
        has_strong_signal = True

    # Soft signals: only meaningful when paired with a strong signal,
    # otherwise a totally flat window would still light them up.
    recent_high = max(highs[-5:])
    recent_low = min(lows[-5:])
    full_high = max(highs)
    full_low = min(lows)
    if has_strong_signal:
        if abs(recent_high - full_high) <= atr_val * 0.5:
            reasons.append("near_window_high")
        if abs(recent_low - full_low) <= atr_val * 0.5:
            reasons.append("near_window_low")

    if not has_strong_signal:
        reasons.append("no_strong_signal_in_window")
    return CandidateDecision(has_strong_signal, reasons)


__all__ = ["CandidateDecision", "is_candidate"]
