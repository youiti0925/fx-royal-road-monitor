"""ATR (Average True Range) computation for the live layer.

Wilder's ATR. ``period`` defaults to 14.
"""

from __future__ import annotations

from .candle import Candle


def true_ranges(candles: list[Candle]) -> list[float]:
    if not candles:
        return []
    out: list[float] = []
    prev_close: float | None = None
    for c in candles:
        if prev_close is None:
            tr = c.h - c.l
        else:
            tr = max(c.h - c.l, abs(c.h - prev_close), abs(c.l - prev_close))
        out.append(tr)
        prev_close = c.c
    return out


def atr(candles: list[Candle], *, period: int = 14) -> float:
    """Wilder's ATR.

    Returns 0.0 if ``len(candles) < period``. The caller should treat 0.0
    as "ATR unavailable" rather than as a real measurement.
    """
    if period <= 0:
        raise ValueError("period must be positive")
    if len(candles) < period:
        return 0.0
    trs = true_ranges(candles)
    seed = sum(trs[:period]) / period
    cur = seed
    for tr in trs[period:]:
        cur = (cur * (period - 1) + tr) / period
    return cur


__all__ = ["atr", "true_ranges"]
