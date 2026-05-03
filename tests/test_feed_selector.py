from __future__ import annotations

from pathlib import Path

from fx_monitor.data.feed_selector import load_market_snapshot_from_env

FIXTURES = Path(__file__).parent / "fixtures"


def test_feed_selector_csv(monkeypatch):
    monkeypatch.setenv("FX_MONITOR_FEED", "csv")
    monkeypatch.setenv("FX_MONITOR_CSV_PATH", str(FIXTURES / "ohlc_sample.csv"))
    monkeypatch.setenv("FX_MONITOR_SYMBOL", "EURUSD=X")
    monkeypatch.setenv("FX_MONITOR_TIMEFRAME", "M5")

    s = load_market_snapshot_from_env()
    assert len(s.candles) == 5
    assert s.last_close == 1.0990


def test_feed_selector_unsupported_returns_warning(monkeypatch):
    monkeypatch.setenv("FX_MONITOR_FEED", "badfeed")
    s = load_market_snapshot_from_env()
    assert s.is_empty is True
    assert s.warnings
    assert "unsupported_feed:badfeed" in s.warnings[0]


def test_feed_selector_default_fixture_returns_warning(monkeypatch):
    monkeypatch.delenv("FX_MONITOR_FEED", raising=False)
    s = load_market_snapshot_from_env()
    # ``fixture`` is not handled by the selector — the rich-payload path
    # uses FX_MONITOR_FIXTURE_PATH instead. Selector returns empty + warning.
    assert s.is_empty is True
    assert any("unsupported_feed" in w for w in s.warnings)


def test_feed_selector_yahoo_without_yfinance_returns_warning(monkeypatch):
    """Even if yfinance isn't installed, the selector must not raise."""
    monkeypatch.setenv("FX_MONITOR_FEED", "yahoo")
    monkeypatch.setenv("FX_MONITOR_SYMBOL", "EURUSD=X")
    monkeypatch.setenv("FX_MONITOR_TIMEFRAME", "M5")

    # Force the import inside yahoo_feed to fail by hiding the module.
    import sys

    monkeypatch.setitem(sys.modules, "yfinance", None)
    s = load_market_snapshot_from_env()
    assert s.is_empty is True
    assert s.warnings
    # Either import_failed (when really missing) or download_failed (when
    # the patched ``None`` is hit). Both are acceptable; the contract is
    # "no raise, snapshot has a warning".
    assert any(
        "yfinance" in w or "yahoo" in w for w in s.warnings
    )
