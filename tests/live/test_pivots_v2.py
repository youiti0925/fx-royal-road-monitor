from __future__ import annotations

from datetime import datetime, timezone

from fx_monitor.live.candle import Candle
from fx_monitor.live.pivots_v2 import detect_multi_scale_pivots


def _c(i: int, h: float, lo: float) -> Candle:
    return Candle(
        t=datetime.fromtimestamp(i * 300, tz=timezone.utc),
        o=(h + lo) / 2,
        h=h,
        l=lo,
        c=(h + lo) / 2,
        v=100.0,
    )


def test_no_pivots_when_series_too_short():
    cs = [_c(i, 1.0, 0.9) for i in range(2)]
    assert detect_multi_scale_pivots(cs, atr_m5=0.0) == []


def test_tie_tolerant_detection_at_micro_scale():
    """The legacy detector dropped pivots on equal-value neighbours; v2 keeps them."""
    highs = [1.00, 1.05, 1.10, 1.10, 1.05, 1.00, 0.95, 0.90, 0.95, 1.00]
    lows = [h - 0.05 for h in highs]
    cs = [_c(i, h, lo) for i, (h, lo) in enumerate(zip(highs, lows))]
    pivots = detect_multi_scale_pivots(cs, atr_m5=0.0)
    highs_detected = [p for p in pivots if p.kind == "HIGH"]
    # Indices 2 and 3 both equal 1.10 — both should be detected at micro scale
    # (a peak with a tying neighbour still qualifies under the relaxed rule).
    assert any(p.index == 2 for p in highs_detected)


def test_atr_filter_suppresses_micro_noise():
    # Tiny oscillation: peak-to-trough only 0.001, ATR=1.0, ratio=0.5 -> filtered.
    highs = [1.000, 1.001, 1.000, 1.001, 1.000, 1.001, 1.000]
    lows = [h - 0.001 for h in highs]
    cs = [_c(i, h, lo) for i, (h, lo) in enumerate(zip(highs, lows))]
    pivots = detect_multi_scale_pivots(cs, atr_m5=1.0, min_swing_atr_ratio=0.5)
    assert pivots == []


def test_multi_scale_keeps_largest_label_per_index():
    # Construct a clear major peak surrounded by quieter context so it
    # qualifies at micro, swing, and major windows.
    highs = (
        [1.00, 1.01, 1.02, 1.03, 1.04, 1.05, 1.06, 1.07, 1.08, 1.09]
        + [1.20]  # peak at index 10
        + [1.09, 1.08, 1.07, 1.06, 1.05, 1.04, 1.03, 1.02, 1.01, 1.00]
    )
    lows = [h - 0.01 for h in highs]
    cs = [_c(i, h, lo) for i, (h, lo) in enumerate(zip(highs, lows))]
    pivots = detect_multi_scale_pivots(cs, atr_m5=0.0)
    peaks = [p for p in pivots if p.kind == "HIGH" and p.index == 10]
    assert len(peaks) == 1
    assert peaks[0].scale == "major"


def test_pivots_record_timestamp_and_strength():
    highs = [1.0, 1.1, 1.2, 1.1, 1.0]
    lows = [h - 0.05 for h in highs]
    cs = [_c(i, h, lo) for i, (h, lo) in enumerate(zip(highs, lows))]
    pivots = detect_multi_scale_pivots(cs, atr_m5=0.0)
    assert pivots
    # Timestamps should be ISO8601 strings of the underlying candles.
    for p in pivots:
        assert "T" in p.timestamp_utc
        assert p.strength > 0
