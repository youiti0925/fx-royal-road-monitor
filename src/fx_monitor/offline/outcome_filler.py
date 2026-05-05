"""Backfill outcomes for PENDING corpus entries.

Live entries enter the corpus with ``outcome.status = "PENDING"``. Once
sufficient bars have elapsed, this module computes their outcome from
fresh price data and updates the store. It is also useful for offline
batch entries created without lookahead (e.g. the most recent ones in
the archive).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from fx_monitor.corpus.outcome import compute_outcome
from fx_monitor.corpus.store import JsonlVectorStore
from fx_monitor.live.candle import Candle


FetchFutureFn = Callable[[str, datetime, int], list[Candle]]


@dataclass
class FillResult:
    examined: int
    filled: int
    skipped_too_recent: int
    failed: int


def _bars_required(timeframe: str, lookahead_bars: int) -> timedelta:
    if timeframe == "M5":
        return timedelta(minutes=5 * lookahead_bars)
    if timeframe == "M15":
        return timedelta(minutes=15 * lookahead_bars)
    if timeframe == "H1":
        return timedelta(hours=lookahead_bars)
    raise ValueError(f"unsupported timeframe: {timeframe}")


def fill_pending_outcomes(
    store: JsonlVectorStore,
    *,
    fetch_future: FetchFutureFn,
    lookahead_bars: int = 60,
    now_utc: datetime | None = None,
) -> FillResult:
    """Update PENDING entries whose lookahead window has elapsed.

    ``fetch_future(symbol, asof_utc, lookahead_bars)`` returns the next
    ``lookahead_bars`` candles after ``asof_utc``. It is supplied by the
    caller so this module is testable without a network/yfinance call.
    """
    now = now_utc or datetime.now(timezone.utc)
    examined = 0
    filled = 0
    skipped = 0
    failed = 0

    for entry in store.pending_outcomes():
        examined += 1
        required_age = _bars_required(entry.timeframe, lookahead_bars)
        asof = entry.asof_utc
        if asof.tzinfo is None:
            asof = asof.replace(tzinfo=timezone.utc)
        if now - asof < required_age:
            skipped += 1
            continue
        try:
            future = fetch_future(entry.symbol, asof, lookahead_bars)
            outcome = compute_outcome(
                entry,
                future,
                max_bars=lookahead_bars,
                now_utc=now,
            )
            if outcome.status == "PENDING":
                # fetch returned nothing usable
                failed += 1
                continue
            store.update_outcome(entry.entry_id, outcome)
            filled += 1
        except Exception:  # pragma: no cover
            failed += 1
    return FillResult(
        examined=examined,
        filled=filled,
        skipped_too_recent=skipped,
        failed=failed,
    )


__all__ = ["fill_pending_outcomes", "FillResult", "FetchFutureFn"]
