"""Forex Factory weekly economic calendar fetcher.

Free public JSON endpoint. No API key required. Provides upcoming
high / medium / low impact economic events with currency, date, and
forecast / previous values.

The fetch is cached per-day under ``data/calendar/`` so we never hammer
the source. The cache is the single source of truth at runtime; the
fetch is only triggered when the cache is missing or stale.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

ImpactLevel = Literal["LOW", "MEDIUM", "HIGH", "HOLIDAY", "OTHER"]

FOREX_FACTORY_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
USER_AGENT = "Mozilla/5.0 (compatible; fx-royal-road-monitor/1.0)"


@dataclass(frozen=True)
class EconomicEvent:
    """Normalised economic-calendar event."""

    title: str
    currency: str
    impact: ImpactLevel
    starts_at_utc: datetime
    forecast: str
    previous: str


def _normalise_impact(raw: str) -> ImpactLevel:
    s = (raw or "").strip().lower()
    if s == "high":
        return "HIGH"
    if s == "medium":
        return "MEDIUM"
    if s == "low":
        return "LOW"
    if s == "holiday":
        return "HOLIDAY"
    return "OTHER"


def _parse_event(raw: dict) -> EconomicEvent | None:
    """Parse a single Forex Factory record into our normalised form.

    Returns ``None`` if the record is malformed (missing required keys
    or unparseable date).
    """
    try:
        date_str = raw.get("date") or ""
        # Forex Factory dates are ISO 8601 with explicit offset (-04:00).
        starts_at = datetime.fromisoformat(date_str)
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=timezone.utc)
        else:
            starts_at = starts_at.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None
    title = raw.get("title") or ""
    if not title:
        return None
    return EconomicEvent(
        title=title,
        currency=(raw.get("country") or "").upper(),
        impact=_normalise_impact(raw.get("impact") or ""),
        starts_at_utc=starts_at,
        forecast=raw.get("forecast") or "",
        previous=raw.get("previous") or "",
    )


def fetch_weekly_calendar(
    *,
    timeout_seconds: int = 15,
    url: str = FOREX_FACTORY_URL,
) -> list[EconomicEvent]:
    """Fetch the live Forex Factory weekly calendar.

    Returns the parsed events. Raises :class:`RuntimeError` on network
    failure so the caller can fall back to a cached file.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = json.load(resp)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        raise RuntimeError(f"forex_factory fetch failed: {exc}") from exc
    out: list[EconomicEvent] = []
    for r in raw:
        ev = _parse_event(r)
        if ev is not None:
            out.append(ev)
    return out


def cache_path(root: Path | str = "data/calendar") -> Path:
    return Path(root) / "ff_weekly.json"


def load_cached_calendar(
    cache_root: Path | str = "data/calendar",
) -> list[EconomicEvent]:
    p = cache_path(cache_root)
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    out: list[EconomicEvent] = []
    for r in raw.get("events", []):
        try:
            out.append(
                EconomicEvent(
                    title=r["title"],
                    currency=r["currency"],
                    impact=r["impact"],
                    starts_at_utc=datetime.fromisoformat(r["starts_at_utc"]),
                    forecast=r.get("forecast", ""),
                    previous=r.get("previous", ""),
                )
            )
        except (KeyError, ValueError):
            continue
    return out


def save_cached_calendar(
    events: list[EconomicEvent],
    *,
    cache_root: Path | str = "data/calendar",
    fetched_at_utc: datetime | None = None,
) -> Path:
    fetched_at_utc = fetched_at_utc or datetime.now(timezone.utc)
    p = cache_path(cache_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "ff_weekly_v1",
        "fetched_at_utc": fetched_at_utc.isoformat(),
        "events": [
            {
                "title": e.title,
                "currency": e.currency,
                "impact": e.impact,
                "starts_at_utc": e.starts_at_utc.isoformat(),
                "forecast": e.forecast,
                "previous": e.previous,
            }
            for e in events
        ],
    }
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def is_cache_stale(
    cache_root: Path | str = "data/calendar",
    *,
    max_age_hours: int = 12,
    now_utc: datetime | None = None,
) -> bool:
    p = cache_path(cache_root)
    if not p.exists():
        return True
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(raw["fetched_at_utc"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return True
    now_utc = now_utc or datetime.now(timezone.utc)
    return (now_utc - fetched_at) > timedelta(hours=max_age_hours)


def refresh_cache_if_stale(
    *,
    cache_root: Path | str = "data/calendar",
    max_age_hours: int = 12,
    now_utc: datetime | None = None,
) -> tuple[list[EconomicEvent], str]:
    """Return (events, source) where source is 'fetched' or 'cached' or 'empty'."""
    if is_cache_stale(cache_root, max_age_hours=max_age_hours, now_utc=now_utc):
        try:
            events = fetch_weekly_calendar()
            save_cached_calendar(events, cache_root=cache_root, fetched_at_utc=now_utc)
            return events, "fetched"
        except RuntimeError:
            cached = load_cached_calendar(cache_root)
            return cached, "cached" if cached else "empty"
    return load_cached_calendar(cache_root), "cached"


__all__ = [
    "EconomicEvent",
    "ImpactLevel",
    "FOREX_FACTORY_URL",
    "fetch_weekly_calendar",
    "load_cached_calendar",
    "save_cached_calendar",
    "is_cache_stale",
    "refresh_cache_if_stale",
    "cache_path",
]
