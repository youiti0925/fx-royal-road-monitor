"""Tests for fx_monitor.live.indicators.

These cover the indicator calculations referenced by doctrine v7
procedure_steps that were previously left as UNKNOWN. Each
indicator must produce a sensible value or None when the lookback
isn't long enough.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fx_monitor.live.candle import Candle
from fx_monitor.live.indicators import (
    compute_bbands,
    compute_ema,
    compute_fib_levels,
    compute_indicator_snapshot,
    compute_ma_stack,
    compute_macd,
    compute_rsi,
    compute_sma,
    find_round_numbers_nearby,
)


def _candles_constant(n: int, price: float) -> list[Candle]:
    base = datetime(2026, 4, 27, tzinfo=timezone.utc)
    return [
        Candle(t=base + timedelta(minutes=5 * i),
               o=price, h=price, l=price, c=price, v=0.0)
        for i in range(n)
    ]


def _candles_ramp(n: int, start: float, step: float) -> list[Candle]:
    """Linearly rising / falling close prices."""
    base = datetime(2026, 4, 27, tzinfo=timezone.utc)
    out = []
    for i in range(n):
        p = start + step * i
        out.append(Candle(
            t=base + timedelta(minutes=5 * i),
            o=p, h=p + 0.0001, l=p - 0.0001, c=p, v=0.0,
        ))
    return out


def test_sma_returns_simple_average_of_last_period():
    candles = _candles_ramp(20, 1.17000, 0.0001)  # 1.17000 .. 1.17000+0.0001*19
    sma = compute_sma(candles, period=20)
    expected = (1.17000 + 1.17000 + 0.0001 * 19) / 2
    assert sma is not None
    assert abs(sma - expected) < 1e-6


def test_sma_returns_none_when_not_enough_candles():
    assert compute_sma(_candles_constant(10, 1.17000), period=20) is None


def test_ema_with_period_5_constant_input():
    candles = _candles_constant(30, 1.17000)
    assert abs(compute_ema(candles, 5) - 1.17000) < 1e-9


def test_ma_stack_reflects_input_lengths():
    short = _candles_constant(60, 1.17000)
    ms = compute_ma_stack(short)
    assert ms.sma20 is not None
    assert ms.sma75 is None
    assert ms.ema200 is None


def test_bbands_computes_mean_and_sigma():
    candles = _candles_ramp(20, 1.17000, 0.0001)
    bb = compute_bbands(candles, period=20, sigma=2.0, atr_pip=2.0)
    assert bb is not None
    expected_mean = (1.17000 + 1.17000 + 0.0001 * 19) / 2
    assert abs(bb.middle - expected_mean) < 1e-6
    assert bb.upper > bb.middle > bb.lower
    assert bb.width_pip > 0


def test_bbands_returns_none_when_short():
    assert compute_bbands(_candles_constant(10, 1.17000)) is None


def test_rsi_constant_input_returns_full_or_neutral_value():
    """All-equal closes mean both gain and loss are zero, so RSI is 100 by
    convention (no losses)."""
    candles = _candles_constant(30, 1.17000)
    rsi = compute_rsi(candles)
    assert rsi == 100.0


def test_rsi_strict_uptrend_is_high():
    candles = _candles_ramp(30, 1.17000, 0.0002)
    rsi = compute_rsi(candles)
    assert rsi is not None
    assert rsi > 70


def test_rsi_strict_downtrend_is_low():
    candles = _candles_ramp(30, 1.17500, -0.0002)
    rsi = compute_rsi(candles)
    assert rsi is not None
    assert rsi < 30


def test_macd_returns_none_when_too_short():
    assert compute_macd(_candles_constant(20, 1.17000)) is None


def test_macd_returns_finite_values_on_long_series():
    candles = _candles_ramp(80, 1.17000, 0.0001)
    macd = compute_macd(candles)
    assert macd is not None
    # Numerical sanity — macd line should be positive for an uptrend.
    assert macd.macd >= 0


def test_fib_levels_anchor_to_window_extremes():
    candles = _candles_ramp(30, 1.17000, -0.0001)
    fib = compute_fib_levels(candles)
    assert fib is not None
    # Highest is the very first candle, lowest is the last.
    assert fib.anchor_high >= candles[0].h
    assert fib.anchor_low <= candles[-1].l
    # 50% should sit between
    assert fib.anchor_low <= fib.fib_500 <= fib.anchor_high


def test_round_numbers_returned_within_radius():
    rns = find_round_numbers_nearby(1.17357, granularity_pips=50, radius_pips=80)
    # 1.17000 (357 pip... actually 35.7 pip away) and 1.17500 (14.3 pip away)
    # should both qualify under 80-pip radius.
    assert any(abs(r - 1.17000) < 1e-6 for r in rns)
    assert any(abs(r - 1.17500) < 1e-6 for r in rns)


def test_indicator_snapshot_combines_everything():
    candles = _candles_ramp(60, 1.17000, 0.0001)
    snap = compute_indicator_snapshot(candles, atr_pip=2.0)
    assert snap.ma.sma20 is not None
    assert snap.bb is not None
    assert snap.rsi14 is not None
    assert snap.fib is not None
    assert snap.round_numbers_nearby
