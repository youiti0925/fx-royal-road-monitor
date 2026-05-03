"""Conservative pivot detection.

Pure observation: returns local highs/lows from a :class:`MarketSnapshot`.
Does **not** make any trading decision.
"""

from __future__ import annotations

from fx_monitor.core.models import MarketSnapshot, PivotPoint


def detect_simple_pivots(
    snapshot: MarketSnapshot,
    *,
    left: int = 2,
    right: int = 2,
    max_pivots: int = 30,
) -> list[PivotPoint]:
    candles = snapshot.candles
    if len(candles) < left + right + 1:
        return []

    pivots: list[PivotPoint] = []

    for i in range(left, len(candles) - right):
        window = candles[i - left : i + right + 1]
        c = candles[i]
        highs = [x.high for x in window]
        lows = [x.low for x in window]

        if c.high == max(highs) and highs.count(c.high) == 1:
            pivots.append(
                PivotPoint(
                    index=i,
                    timestamp_utc=c.timestamp_utc,
                    price=c.high,
                    kind="HIGH",
                    strength=left + right,
                )
            )

        if c.low == min(lows) and lows.count(c.low) == 1:
            pivots.append(
                PivotPoint(
                    index=i,
                    timestamp_utc=c.timestamp_utc,
                    price=c.low,
                    kind="LOW",
                    strength=left + right,
                )
            )

    return pivots[-max_pivots:]


__all__ = ["detect_simple_pivots"]
