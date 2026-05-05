"""Backfill outcomes for PENDING corpus entries.

The actual fetching of future candles is delegated to a callable. From
the CLI we use yfinance via :mod:`fx_monitor.offline.ohlc_archive`; from
tests we inject a stub. This keeps the tool importable when yfinance
is not installed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fx_monitor.corpus.store import JsonlVectorStore
from fx_monitor.live.candle import Candle
from fx_monitor.offline.outcome_filler import fill_pending_outcomes

from ._paths import corpus_root


def _yfinance_fetch_future(symbol: str, asof: datetime, n: int) -> list[Candle]:
    from fx_monitor.offline.ohlc_archive import fetch_ohlc

    if asof.tzinfo is None:
        asof = asof.replace(tzinfo=timezone.utc)
    end = asof + timedelta(minutes=5 * (n + 5))
    result = fetch_ohlc(
        symbol,
        timeframe="5m",
        start=asof,
        end=end,
        use_cache=True,
    )
    future = [c for c in result.candles if c.t > asof]
    return future[:n]


def update_outcomes(
    *,
    corpus_name: str = "default",
    lookahead_bars: int = 60,
    fetch_future=None,
    now_utc: datetime | None = None,
) -> dict:
    store = JsonlVectorStore(corpus_root(corpus_name))
    fetcher = fetch_future or _yfinance_fetch_future
    result = fill_pending_outcomes(
        store,
        fetch_future=fetcher,
        lookahead_bars=lookahead_bars,
        now_utc=now_utc,
    )
    return {
        "examined": result.examined,
        "filled": result.filled,
        "skipped_too_recent": result.skipped_too_recent,
        "failed": result.failed,
        "corpus_size": len(store),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fx_monitor.tools.update_outcomes")
    p.add_argument("--corpus-name", default="default")
    p.add_argument("--lookahead-bars", type=int, default=60)
    args = p.parse_args(argv)

    info = update_outcomes(
        corpus_name=args.corpus_name,
        lookahead_bars=args.lookahead_bars,
    )
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
