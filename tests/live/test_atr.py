from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fx_monitor.live.atr import atr, true_ranges
from fx_monitor.live.candle import Candle


def _candles(prices: list[tuple[float, float, float, float]]) -> list[Candle]:
    out: list[Candle] = []
    for i, (o, h, lo, c) in enumerate(prices):
        out.append(
            Candle(
                t=datetime.fromtimestamp(i * 300, tz=timezone.utc),
                o=o,
                h=h,
                l=lo,
                c=c,
                v=100.0,
            )
        )
    return out


def test_true_ranges_first_bar_uses_high_low():
    cs = _candles([(1.0, 1.10, 0.95, 1.05), (1.05, 1.20, 1.00, 1.18)])
    trs = true_ranges(cs)
    assert trs[0] == pytest.approx(0.15)
    # second bar TR = max(0.20, |1.20-1.05|, |1.00-1.05|) = 0.20
    assert trs[1] == pytest.approx(0.20)


def test_atr_returns_zero_when_too_few_bars():
    cs = _candles([(1.0, 1.1, 0.9, 1.05)] * 5)
    assert atr(cs, period=14) == 0.0


def test_atr_period_must_be_positive():
    with pytest.raises(ValueError):
        atr([], period=0)


def test_atr_constant_range_equals_range():
    # 20 bars, range 0.10 each, should yield ATR ≈ 0.10
    cs = _candles([(1.0, 1.10, 1.00, 1.05)] * 20)
    val = atr(cs, period=14)
    assert val == pytest.approx(0.10)
