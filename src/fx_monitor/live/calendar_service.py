"""Bridge between the offline-fetched economic calendar and the live
``MarketAnalysisPackV2.calendar_events_within_60min`` slot.

The offline layer (:mod:`fx_monitor.offline.forex_factory_calendar`)
caches the weekly schedule. The live layer queries that cache for the
specific symbol and asof time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .market_pack_v2 import CalendarEvent


_SYMBOL_CURRENCY_MAP: dict[str, tuple[str, ...]] = {
    "EURUSD=X": ("EUR", "USD"),
    "GBPUSD=X": ("GBP", "USD"),
    "USDJPY=X": ("USD", "JPY"),
    "AUDUSD=X": ("AUD", "USD"),
    "USDCHF=X": ("USD", "CHF"),
    "NZDUSD=X": ("NZD", "USD"),
    "USDCAD=X": ("USD", "CAD"),
    "EURJPY=X": ("EUR", "JPY"),
    "GBPJPY=X": ("GBP", "JPY"),
    "AUDJPY=X": ("AUD", "JPY"),
}


def relevant_currencies(symbol: str) -> tuple[str, ...]:
    """Return the FX currencies whose events are relevant to ``symbol``."""
    return _SYMBOL_CURRENCY_MAP.get(symbol, ("USD",))


def events_within_window(
    *,
    symbol: str,
    asof_utc: datetime,
    window_minutes: int = 60,
    include_impacts: Iterable[str] = ("HIGH", "MEDIUM"),
    cache_root: Path | str = "data/calendar",
) -> list[CalendarEvent]:
    """Return calendar events relevant to ``symbol`` within ``window_minutes``
    (forward) of ``asof_utc``.

    Reads the cached calendar produced by the offline fetcher; the
    function does not perform any network call. If the cache is empty
    we return an empty list.
    """
    from fx_monitor.offline.forex_factory_calendar import load_cached_calendar

    events = load_cached_calendar(cache_root)
    if not events:
        return []

    currencies = relevant_currencies(symbol)
    impacts = {i.upper() for i in include_impacts}
    now = asof_utc if asof_utc.tzinfo else asof_utc.replace(tzinfo=timezone.utc)
    horizon_start = now - timedelta(minutes=window_minutes)
    horizon_end = now + timedelta(minutes=window_minutes)

    out: list[CalendarEvent] = []
    for ev in events:
        if ev.currency not in currencies:
            continue
        if ev.impact not in impacts:
            continue
        starts = ev.starts_at_utc
        if starts.tzinfo is None:
            starts = starts.replace(tzinfo=timezone.utc)
        if not (horizon_start <= starts <= horizon_end):
            continue
        minutes_until = int((starts - now).total_seconds() / 60)
        out.append(
            CalendarEvent(
                name=f"{ev.currency} {ev.title}".strip(),
                impact=ev.impact,  # type: ignore[arg-type]
                minutes_until=minutes_until,
            )
        )
    out.sort(key=lambda e: abs(e.minutes_until))
    return out


__all__ = ["events_within_window", "relevant_currencies"]
