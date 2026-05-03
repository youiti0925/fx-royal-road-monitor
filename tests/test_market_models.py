from __future__ import annotations

from datetime import datetime, timezone

from fx_monitor.core.models import MarketCandle, MarketSnapshot


def test_market_candle_ohlc_order_valid():
    c = MarketCandle(
        timestamp_utc=datetime.now(timezone.utc),
        open=1.0,
        high=1.2,
        low=0.9,
        close=1.1,
    )
    assert c.validate_ohlc_order() is True


def test_market_candle_ohlc_order_invalid_does_not_raise():
    # high < open: order invalid, but pydantic must not raise.
    c = MarketCandle(
        timestamp_utc=datetime.now(timezone.utc),
        open=1.5,
        high=1.0,
        low=0.9,
        close=1.1,
    )
    assert c.validate_ohlc_order() is False


def test_market_snapshot_last_close():
    c = MarketCandle(
        timestamp_utc=datetime.now(timezone.utc),
        open=1.0,
        high=1.2,
        low=0.9,
        close=1.1,
    )
    s = MarketSnapshot(symbol="EURUSD=X", timeframe="M5", source="test", candles=[c])
    assert s.is_empty is False
    assert s.last_close == 1.1


def test_market_snapshot_empty_defaults():
    s = MarketSnapshot(symbol="EURUSD=X", timeframe="M5", source="test")
    assert s.is_empty is True
    assert s.last_close is None
    assert s.warnings == []
