"""Choose a market data feed by environment variable.

``FX_MONITOR_FEED`` controls the source:

- ``fixture``: no live data here — the run_once script's fixture path is
  the rich-payload route. ``feed_selector`` returns an empty snapshot with
  an ``unsupported_feed`` warning so callers know to use the other path.
- ``csv``:    read OHLC from ``FX_MONITOR_CSV_PATH``.
- ``yahoo``:  fetch via the optional yfinance feed.

Anything else returns an empty snapshot with a warning. Never raises.
"""

from __future__ import annotations

import os

from fx_monitor.core.models import MarketSnapshot

from .csv_feed import load_ohlc_csv
from .yahoo_feed import fetch_yahoo_ohlc


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_market_snapshot_from_env() -> MarketSnapshot:
    feed = os.getenv("FX_MONITOR_FEED", "fixture").lower()
    symbol = os.getenv("FX_MONITOR_SYMBOL", "EURUSD=X")
    timeframe = os.getenv("FX_MONITOR_TIMEFRAME", "M5")
    max_candles = _int_env("FX_MONITOR_MAX_CANDLES", 300)

    if feed == "csv":
        path = os.getenv("FX_MONITOR_CSV_PATH", "")
        return load_ohlc_csv(
            path,
            symbol=symbol,
            timeframe=timeframe,
            max_candles=max_candles,
        )

    if feed == "yahoo":
        return fetch_yahoo_ohlc(
            symbol=symbol,
            timeframe=timeframe,
            max_candles=max_candles,
        )

    return MarketSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        source=f"unsupported:{feed}",
        candles=[],
        warnings=[f"unsupported_feed:{feed}"],
    )


__all__ = ["load_market_snapshot_from_env"]
