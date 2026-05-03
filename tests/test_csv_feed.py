from __future__ import annotations

from pathlib import Path

from fx_monitor.data.csv_feed import load_ohlc_csv

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_ohlc_csv_sample():
    s = load_ohlc_csv(
        FIXTURES / "ohlc_sample.csv",
        symbol="EURUSD=X",
        timeframe="M5",
    )
    assert s.symbol == "EURUSD=X"
    assert s.timeframe == "M5"
    assert s.source.startswith("csv:")
    assert len(s.candles) == 5
    assert s.last_close == 1.0990
    assert s.warnings == []


def test_load_ohlc_csv_missing_file_returns_empty_snapshot(tmp_path):
    s = load_ohlc_csv(
        tmp_path / "missing.csv",
        symbol="EURUSD=X",
        timeframe="M5",
    )
    assert s.is_empty is True
    assert s.warnings
    assert "csv_not_found" in s.warnings[0]


def test_load_ohlc_csv_max_candles_truncates(tmp_path):
    src = FIXTURES / "ohlc_sample.csv"
    s = load_ohlc_csv(
        src, symbol="EURUSD=X", timeframe="M5", max_candles=2
    )
    assert len(s.candles) == 2
    # Truncation keeps the most recent candles.
    assert s.last_close == 1.0990


def test_load_ohlc_csv_bad_row_warns_but_continues(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "timestamp_utc,open,high,low,close,volume\n"
        "2026-05-03T12:00:00+00:00,1.10,1.11,1.09,1.105,100\n"
        "not-a-timestamp,foo,bar,baz,qux,quux\n"
        "2026-05-03T12:05:00+00:00,1.105,1.12,1.10,1.115,110\n",
        encoding="utf-8",
    )
    s = load_ohlc_csv(bad, symbol="X", timeframe="M5")
    assert len(s.candles) == 2
    assert any("row_parse_failed" in w for w in s.warnings)
