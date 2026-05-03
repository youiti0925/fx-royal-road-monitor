"""Optional Yahoo Finance OHLC feed via yfinance.

``yfinance`` is an optional extra (``pip install -e .[market]``). If it isn't
installed, or the network is down, or the response is empty, we return an
empty :class:`MarketSnapshot` with a descriptive warning. The monitor never
raises out of this module.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fx_monitor.core.models import MarketCandle, MarketSnapshot


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _empty(symbol: str, timeframe: str, warning: str) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        source="yahoo",
        candles=[],
        fetched_at_utc=_now_utc(),
        warnings=[warning],
    )


def fetch_yahoo_ohlc(
    *,
    symbol: str,
    timeframe: str,
    period: str = "5d",
    max_candles: int | None = 300,
) -> MarketSnapshot:
    try:
        import yfinance as yf
    except Exception as exc:  # pragma: no cover - exercised when yfinance absent
        return _empty(symbol, timeframe, f"yfinance_import_failed:{type(exc).__name__}")

    interval = _map_timeframe_to_yahoo_interval(timeframe)
    warnings: list[str] = []

    try:
        df = yf.download(
            symbol,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=False,
        )
    except Exception as exc:
        return _empty(symbol, timeframe, f"yahoo_download_failed:{type(exc).__name__}")

    if df is None or getattr(df, "empty", True):
        return _empty(symbol, timeframe, "yahoo_empty_dataframe")

    candles: list[MarketCandle] = []
    try:
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)

            candle = MarketCandle(
                timestamp_utc=ts,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]) if "Volume" in row else None,
            )
            if not candle.validate_ohlc_order():
                warnings.append(f"ohlc_order_invalid:{ts.isoformat()}")
            candles.append(candle)
    except Exception as exc:
        return _empty(symbol, timeframe, f"yahoo_parse_failed:{type(exc).__name__}")

    candles.sort(key=lambda c: c.timestamp_utc)
    if max_candles is not None and max_candles > 0:
        candles = candles[-max_candles:]

    return MarketSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        source="yahoo",
        candles=candles,
        fetched_at_utc=_now_utc(),
        warnings=warnings,
    )


def _map_timeframe_to_yahoo_interval(timeframe: str) -> str:
    tf = (timeframe or "").lower()
    mapping = {
        "1m": "1m", "m1": "1m",
        "5m": "5m", "m5": "5m",
        "15m": "15m", "m15": "15m",
        "30m": "30m", "m30": "30m",
        "1h": "1h", "h1": "1h",
        "1d": "1d", "d1": "1d",
    }
    return mapping.get(tf, "5m")


__all__ = ["fetch_yahoo_ohlc"]
