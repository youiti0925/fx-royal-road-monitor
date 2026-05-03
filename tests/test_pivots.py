from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fx_monitor.analysis.pivots import detect_simple_pivots
from fx_monitor.core.models import MarketCandle, MarketSnapshot


def _snapshot(closes: list[float]) -> MarketSnapshot:
    candles = []
    base = datetime(2026, 5, 3, tzinfo=timezone.utc)
    for i, price in enumerate(closes):
        candles.append(
            MarketCandle(
                timestamp_utc=base + timedelta(minutes=5 * i),
                open=price,
                high=price + 0.01,
                low=price - 0.01,
                close=price,
            )
        )
    return MarketSnapshot(symbol="X", timeframe="M5", source="test", candles=candles)


def test_detect_simple_pivots_returns_highs_and_lows():
    s = _snapshot([1.0, 1.1, 1.0, 1.2, 1.0, 1.1, 1.0])
    pivots = detect_simple_pivots(s, left=1, right=1)
    assert pivots
    assert any(p.kind == "HIGH" for p in pivots)
    assert any(p.kind == "LOW" for p in pivots)


def test_detect_simple_pivots_too_short_returns_empty():
    s = _snapshot([1.0])
    assert detect_simple_pivots(s, left=2, right=2) == []


def test_detect_simple_pivots_max_pivots_truncates():
    s = _snapshot([1.0, 1.1, 1.0, 1.2, 1.0, 1.3, 1.0, 1.4, 1.0, 1.5, 1.0])
    pivots = detect_simple_pivots(s, left=1, right=1, max_pivots=3)
    assert len(pivots) == 3
