from __future__ import annotations

from datetime import datetime, timezone

from fx_monitor.offline.ohlc_archive import load_ohlc_records


def test_load_ohlc_records_parses_dicts():
    records = [
        {
            "t": "2026-05-04T10:00:00+00:00",
            "o": 1.10,
            "h": 1.11,
            "l": 1.09,
            "c": 1.105,
            "v": 1234.0,
        },
        {
            "t": datetime(2026, 5, 4, 10, 5, tzinfo=timezone.utc),
            "o": 1.105,
            "h": 1.115,
            "l": 1.10,
            "c": 1.11,
            "v": None,
        },
    ]
    candles = load_ohlc_records(records)
    assert len(candles) == 2
    assert candles[0].o == 1.10
    assert candles[0].t.tzinfo is not None
    assert candles[1].v is None


def test_load_ohlc_records_assumes_utc_when_naive():
    records = [
        {
            "t": datetime(2026, 5, 4, 10, 0),  # naive
            "o": 1.10,
            "h": 1.11,
            "l": 1.09,
            "c": 1.105,
            "v": 100.0,
        }
    ]
    candles = load_ohlc_records(records)
    assert candles[0].t.tzinfo == timezone.utc
