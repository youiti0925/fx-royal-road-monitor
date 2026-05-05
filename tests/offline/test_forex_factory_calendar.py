from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fx_monitor.offline.forex_factory_calendar import (
    EconomicEvent,
    _normalise_impact,
    _parse_event,
    is_cache_stale,
    load_cached_calendar,
    save_cached_calendar,
)


def test_normalise_impact_maps_known_values():
    assert _normalise_impact("High") == "HIGH"
    assert _normalise_impact("medium") == "MEDIUM"
    assert _normalise_impact("LOW") == "LOW"
    assert _normalise_impact("Holiday") == "HOLIDAY"
    assert _normalise_impact("") == "OTHER"


def test_parse_event_returns_none_for_bad_date():
    assert _parse_event({"title": "x", "country": "USD", "date": "not-a-date"}) is None


def test_parse_event_normalises_offset_to_utc():
    raw = {
        "title": "NFP",
        "country": "USD",
        "date": "2026-05-04T08:30:00-04:00",
        "impact": "High",
        "forecast": "200K",
        "previous": "180K",
    }
    ev = _parse_event(raw)
    assert ev is not None
    assert ev.starts_at_utc == datetime(2026, 5, 4, 12, 30, tzinfo=timezone.utc)
    assert ev.impact == "HIGH"
    assert ev.currency == "USD"


def test_save_and_load_round_trip(tmp_path: Path):
    events = [
        EconomicEvent(
            title="CPI", currency="USD", impact="HIGH",
            starts_at_utc=datetime(2026, 5, 5, 13, 30, tzinfo=timezone.utc),
            forecast="3.5%", previous="3.4%",
        ),
        EconomicEvent(
            title="GDP", currency="EUR", impact="MEDIUM",
            starts_at_utc=datetime(2026, 5, 6, 9, 0, tzinfo=timezone.utc),
            forecast="0.2%", previous="0.1%",
        ),
    ]
    save_cached_calendar(events, cache_root=tmp_path)
    loaded = load_cached_calendar(tmp_path)
    assert len(loaded) == 2
    assert loaded[0].title == "CPI"
    assert loaded[1].currency == "EUR"


def test_is_cache_stale_when_missing(tmp_path: Path):
    assert is_cache_stale(tmp_path) is True


def test_is_cache_stale_when_old(tmp_path: Path):
    save_cached_calendar(
        [], cache_root=tmp_path,
        fetched_at_utc=datetime.now(timezone.utc) - timedelta(hours=24),
    )
    assert is_cache_stale(tmp_path, max_age_hours=12) is True


def test_is_cache_fresh_when_recent(tmp_path: Path):
    save_cached_calendar(
        [], cache_root=tmp_path,
        fetched_at_utc=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    assert is_cache_stale(tmp_path, max_age_hours=12) is False
