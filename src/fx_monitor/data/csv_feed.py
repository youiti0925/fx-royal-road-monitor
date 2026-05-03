"""Read-only CSV OHLC feed.

Returns a :class:`MarketSnapshot` no matter what — missing files, malformed
rows, and out-of-order OHLC are surfaced via ``warnings`` rather than raised,
so a 5-minute monitor never crashes on a bad input.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from fx_monitor.core.models import MarketCandle, MarketSnapshot


def _parse_ts(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _float_col(row: dict[str, str], *names: str) -> float:
    for name in names:
        v = row.get(name)
        if v not in (None, ""):
            return float(v)
    raise KeyError(f"missing columns: {names}")


def _maybe_volume(row: dict[str, str]) -> float | None:
    for name in ("volume", "Volume"):
        v = row.get(name)
        if v not in (None, ""):
            try:
                return float(v)
            except ValueError:
                return None
    return None


def load_ohlc_csv(
    path: str | Path,
    *,
    symbol: str,
    timeframe: str,
    max_candles: int | None = None,
) -> MarketSnapshot:
    p = Path(path)
    warnings: list[str] = []
    candles: list[MarketCandle] = []

    if not p.exists():
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            source=f"csv:{p}",
            candles=[],
            warnings=[f"csv_not_found:{p}"],
        )

    try:
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                try:
                    ts_raw = (
                        row.get("timestamp_utc")
                        or row.get("timestamp")
                        or row.get("Datetime")
                        or row.get("Date")
                        or ""
                    )
                    candle = MarketCandle(
                        timestamp_utc=_parse_ts(ts_raw),
                        open=_float_col(row, "open", "Open"),
                        high=_float_col(row, "high", "High"),
                        low=_float_col(row, "low", "Low"),
                        close=_float_col(row, "close", "Close"),
                        volume=_maybe_volume(row),
                    )
                    if not candle.validate_ohlc_order():
                        warnings.append(f"ohlc_order_invalid:row={i}")
                    candles.append(candle)
                except Exception as exc:
                    warnings.append(f"row_parse_failed:row={i}:{type(exc).__name__}")
    except Exception as exc:
        return MarketSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            source=f"csv:{p}",
            candles=[],
            warnings=[f"csv_read_failed:{type(exc).__name__}"],
        )

    candles.sort(key=lambda c: c.timestamp_utc)
    if max_candles is not None and max_candles > 0:
        candles = candles[-max_candles:]

    return MarketSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        source=f"csv:{p}",
        candles=candles,
        warnings=warnings,
    )


__all__ = ["load_ohlc_csv"]
