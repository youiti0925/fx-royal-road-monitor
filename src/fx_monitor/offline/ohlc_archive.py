"""Historical OHLC archive.

We use yfinance for the production fetch path because it is free,
unauthenticated, and adequate for M5 FX bars. yfinance is an optional
dependency (``[market]`` extra) so the rest of the package stays
importable even if it is not installed — the loader is exposed via a
late import inside the function.

Fetched data is cached as Parquet under ``data/ohlc/`` so subsequent
calls are instant and deterministic. Tests bypass yfinance entirely by
loading from CSV/dict via :func:`load_ohlc_records`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from fx_monitor.live.candle import Candle


@dataclass
class FetchResult:
    candles: list[Candle]
    source: str  # "yfinance" or "cache" or "memory"
    cache_path: Path | None


def _cache_path(root: Path, symbol: str, timeframe: str, start: datetime, end: datetime) -> Path:
    safe_symbol = symbol.replace("=", "_").replace("/", "_")
    name = f"{safe_symbol}_{timeframe}_{start.date()}_{end.date()}.parquet"
    return root / name


def _records_to_candles(records: list[dict]) -> list[Candle]:
    out: list[Candle] = []
    for r in records:
        t = r["t"]
        if isinstance(t, str):
            t = datetime.fromisoformat(t)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        out.append(
            Candle(
                t=t,
                o=float(r["o"]),
                h=float(r["h"]),
                l=float(r["l"]),
                c=float(r["c"]),
                v=float(r["v"]) if r.get("v") is not None else None,
            )
        )
    return out


def load_ohlc_records(records: list[dict]) -> list[Candle]:
    """Load candles from a list of dicts.

    Each dict needs at least ``t, o, h, l, c`` and may include ``v``.
    Useful in tests and for ad-hoc CSV imports without yfinance.
    """
    return _records_to_candles(records)


def fetch_ohlc(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    *,
    cache_root: Path | str = "data/ohlc",
    use_cache: bool = True,
) -> FetchResult:
    """Fetch historical OHLC, preferring cache.

    ``timeframe`` follows yfinance interval syntax (``"5m"``, ``"15m"``,
    ``"1h"`` etc). For our purposes it is "5m".
    """
    cache_root_p = Path(cache_root)
    cache_root_p.mkdir(parents=True, exist_ok=True)
    cache = _cache_path(cache_root_p, symbol, timeframe, start, end)

    if use_cache and cache.exists():
        try:
            import pandas as pd  # type: ignore

            df = pd.read_parquet(cache)
            records = df.to_dict("records")
            return FetchResult(_records_to_candles(records), "cache", cache)
        except Exception:
            # Cache unreadable — fall through to refetch.
            pass

    try:
        import yfinance as yf  # type: ignore
        import pandas as pd  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "yfinance not installed. Install with `pip install '.[market]'` "
            "or pass pre-loaded records via load_ohlc_records()."
        ) from e

    df = yf.download(
        symbol,
        start=start,
        end=end,
        interval=timeframe,
        progress=False,
        auto_adjust=False,
    )
    if df is None or df.empty:
        return FetchResult([], "yfinance", None)

    # yfinance returns a MultiIndex on columns when given a single ticker
    # (("Open", "EURUSD=X"), ...). Flatten it before renaming.
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    df = df.reset_index()
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df.rename(
        columns={
            "Datetime": "t",
            "Date": "t",
            "Open": "o",
            "High": "h",
            "Low": "l",
            "Close": "c",
            "Volume": "v",
        }
    )
    keep = [c for c in ["t", "o", "h", "l", "c", "v"] if c in df.columns]
    df = df[keep]
    if use_cache:
        try:
            df.to_parquet(cache)
        except Exception:
            cache = None  # cache is best-effort

    records = df.to_dict("records")
    return FetchResult(_records_to_candles(records), "yfinance", cache)


__all__ = ["FetchResult", "fetch_ohlc", "load_ohlc_records"]
