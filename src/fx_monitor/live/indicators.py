"""Technical indicators referenced by doctrine v7 procedure_steps.

Why this exists
---------------
The knowledge_pack mentions several indicators (SMA, EMA, Bollinger
Bands, RSI, MACD, Fibonacci retracement, round numbers / キリ番), but
until now the corresponding values were never computed from candles —
the AI judge always wrote "MA 値未供給 → UNKNOWN" and similar. That
made the doctrine steps ``ma_alignment``, ``indicator_environment``,
``divergence_check`` and the round-number filter of
``horizontal_levels`` effectively dead.

This module is the missing computation layer. Each function takes the
same ``candles: list[Candle]`` the rest of ``live`` deals with and
returns a small pydantic-friendly dict (no numpy in the public API to
keep the pack JSON-serialisable).

Conventions
-----------
- All values are at the LAST candle in the input window (= asof).
- Where a sufficient lookback is unavailable, the function returns
  ``None`` rather than an extrapolated value.
- Period parameters default to standard royal-road values (SMA20 /
  SMA75 / EMA200, BB(20, 2σ), RSI14, MACD(12, 26, 9)).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from fx_monitor.live.candle import Candle


# ---------------------------------------------------------------------------
# Moving averages
# ---------------------------------------------------------------------------


def compute_sma(candles: list[Candle], period: int) -> float | None:
    """Simple moving average of close over the last ``period`` candles."""
    if len(candles) < period:
        return None
    return sum(c.c for c in candles[-period:]) / period


def compute_ema(candles: list[Candle], period: int) -> float | None:
    """Exponential moving average of close over the last ``period`` candles."""
    if len(candles) < period:
        return None
    k = 2.0 / (period + 1)
    # Seed with the SMA of the first ``period`` closes for stability.
    seed = sum(c.c for c in candles[:period]) / period
    ema = seed
    for c in candles[period:]:
        ema = c.c * k + ema * (1 - k)
    return ema


@dataclass(frozen=True)
class MAStack:
    """Snapshot of common moving averages at the asof candle."""
    sma20: float | None = None
    sma75: float | None = None
    ema200: float | None = None


def compute_ma_stack(candles: list[Candle]) -> MAStack:
    return MAStack(
        sma20=compute_sma(candles, 20),
        sma75=compute_sma(candles, 75),
        ema200=compute_ema(candles, 200),
    )


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BBands:
    middle: float
    upper: float
    lower: float
    width_pip: float        # (upper - lower) in pips
    width_atr_ratio: float  # width / ATR — squeeze metric


def compute_bbands(
    candles: list[Candle],
    *,
    period: int = 20,
    sigma: float = 2.0,
    pip_size: float = 0.0001,
    atr_pip: float | None = None,
) -> BBands | None:
    """Bollinger Bands at the asof candle.

    ``atr_pip`` (when supplied) is used to compute ``width_atr_ratio`` —
    the standard squeeze metric (width below ~ATR × 1.5 = squeeze).
    """
    if len(candles) < period:
        return None
    closes = [c.c for c in candles[-period:]]
    mean = sum(closes) / period
    var = sum((x - mean) ** 2 for x in closes) / period
    sd = math.sqrt(var)
    upper = mean + sigma * sd
    lower = mean - sigma * sd
    width_pip = (upper - lower) / pip_size
    width_atr_ratio = (width_pip / atr_pip) if (atr_pip and atr_pip > 0) else 0.0
    return BBands(
        middle=mean, upper=upper, lower=lower,
        width_pip=width_pip, width_atr_ratio=width_atr_ratio,
    )


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------


def compute_rsi(candles: list[Candle], period: int = 14) -> float | None:
    """Relative Strength Index, Wilder smoothing, returned at asof."""
    if len(candles) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(candles)):
        diff = candles[i].c - candles[i - 1].c
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    # Initial average over the first ``period`` deltas.
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    # Wilder smoothing for the rest.
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MACDValues:
    macd: float
    signal: float
    histogram: float


def compute_macd(
    candles: list[Candle],
    *,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> MACDValues | None:
    """MACD = EMA(fast) - EMA(slow), signal = EMA(MACD, signal_period)."""
    if len(candles) < slow + signal_period:
        return None
    # Re-implement EMA as a list to compute signal line over MACD series.
    def ema_series(values: list[float], n: int) -> list[float]:
        k = 2.0 / (n + 1)
        out = [values[0]]
        for v in values[1:]:
            out.append(v * k + out[-1] * (1 - k))
        return out

    closes = [c.c for c in candles]
    ema_fast = ema_series(closes, fast)
    ema_slow = ema_series(closes, slow)
    macd_series = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_series = ema_series(macd_series, signal_period)
    return MACDValues(
        macd=macd_series[-1],
        signal=signal_series[-1],
        histogram=macd_series[-1] - signal_series[-1],
    )


# ---------------------------------------------------------------------------
# Fibonacci retracement
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FibLevels:
    """Standard fib retracement levels between an extreme pair."""
    anchor_high: float
    anchor_low: float
    direction: str  # "down" if anchor_high preceded anchor_low in time, else "up"
    fib_236: float
    fib_382: float
    fib_500: float
    fib_618: float
    fib_786: float


def compute_fib_levels(
    candles: list[Candle],
) -> FibLevels | None:
    """Anchor at the window's extreme high and low (in time order).

    direction == 'down': high came BEFORE low → typical for a recent
    decline; retracement levels are *up* from the low.
    direction == 'up': low came BEFORE high → typical for a recent
    rally; retracement levels are *down* from the high.
    """
    if len(candles) < 5:
        return None
    high_idx = max(range(len(candles)), key=lambda i: candles[i].h)
    low_idx = min(range(len(candles)), key=lambda i: candles[i].l)
    h = candles[high_idx].h
    l = candles[low_idx].l
    if h == l:
        return None
    direction = "down" if high_idx < low_idx else "up"
    span = h - l
    return FibLevels(
        anchor_high=h, anchor_low=l, direction=direction,
        fib_236=l + span * 0.236 if direction == "down" else h - span * 0.236,
        fib_382=l + span * 0.382 if direction == "down" else h - span * 0.382,
        fib_500=l + span * 0.500 if direction == "down" else h - span * 0.500,
        fib_618=l + span * 0.618 if direction == "down" else h - span * 0.618,
        fib_786=l + span * 0.786 if direction == "down" else h - span * 0.786,
    )


# ---------------------------------------------------------------------------
# Round numbers (キリ番)
# ---------------------------------------------------------------------------


def find_round_numbers_nearby(
    current_price: float,
    *,
    pip_size: float = 0.0001,
    granularity_pips: int = 50,    # 50 pip = 0.0050 = "kiribans" like 1.17000, 1.17050
    radius_pips: int = 80,
) -> list[float]:
    """Return round-number prices within ``radius_pips`` of ``current_price``.

    ``granularity_pips`` defines what a "round number" is. 100 = the
    biggest kiribans (1.17000, 1.18000); 50 = sub-kiribans; 25 = quarter.
    """
    g = granularity_pips * pip_size
    base = round(current_price / g) * g
    out: list[float] = []
    for k in range(-3, 4):
        rn = base + k * g
        if abs(rn - current_price) <= radius_pips * pip_size + 1e-9:
            out.append(round(rn, 5))
    return sorted(set(out))


# ---------------------------------------------------------------------------
# One-shot wrapper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSnapshot:
    """All doctrine-relevant indicators at the asof candle."""
    ma: MAStack
    bb: BBands | None
    rsi14: float | None
    macd: MACDValues | None
    fib: FibLevels | None
    round_numbers_nearby: tuple[float, ...]


def compute_indicator_snapshot(
    candles: list[Candle],
    *,
    pip_size: float = 0.0001,
    atr_pip: float | None = None,
    current_price: float | None = None,
) -> IndicatorSnapshot:
    cp = current_price if current_price is not None else (candles[-1].c if candles else 0.0)
    return IndicatorSnapshot(
        ma=compute_ma_stack(candles),
        bb=compute_bbands(candles, pip_size=pip_size, atr_pip=atr_pip),
        rsi14=compute_rsi(candles),
        macd=compute_macd(candles),
        fib=compute_fib_levels(candles),
        round_numbers_nearby=tuple(
            find_round_numbers_nearby(cp, pip_size=pip_size)
        ),
    )


__all__ = [
    "MAStack", "BBands", "MACDValues", "FibLevels", "IndicatorSnapshot",
    "compute_sma", "compute_ema", "compute_ma_stack",
    "compute_bbands",
    "compute_rsi",
    "compute_macd",
    "compute_fib_levels",
    "find_round_numbers_nearby",
    "compute_indicator_snapshot",
]
