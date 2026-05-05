from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fx_monitor.live.calendar_service import events_within_window, relevant_currencies
from fx_monitor.offline.forex_factory_calendar import (
    EconomicEvent,
    save_cached_calendar,
)


def test_relevant_currencies_known_pairs():
    assert relevant_currencies("EURUSD=X") == ("EUR", "USD")
    assert relevant_currencies("USDJPY=X") == ("USD", "JPY")
    assert relevant_currencies("UNKNOWN=X") == ("USD",)


def test_events_within_window_filters_by_currency_and_window(tmp_path: Path):
    asof = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    events = [
        # In window for USDJPY (USD currency, 30min ahead)
        EconomicEvent(
            title="NFP", currency="USD", impact="HIGH",
            starts_at_utc=asof + timedelta(minutes=30),
            forecast="", previous="",
        ),
        # Out of window (75min ahead)
        EconomicEvent(
            title="Speech", currency="USD", impact="HIGH",
            starts_at_utc=asof + timedelta(minutes=75),
            forecast="", previous="",
        ),
        # Wrong currency for USDJPY
        EconomicEvent(
            title="ECB Rate", currency="EUR", impact="HIGH",
            starts_at_utc=asof + timedelta(minutes=30),
            forecast="", previous="",
        ),
        # JPY high in window
        EconomicEvent(
            title="BOJ Statement", currency="JPY", impact="HIGH",
            starts_at_utc=asof + timedelta(minutes=15),
            forecast="", previous="",
        ),
    ]
    save_cached_calendar(events, cache_root=tmp_path)
    matches = events_within_window(
        symbol="USDJPY=X", asof_utc=asof, window_minutes=60, cache_root=tmp_path
    )
    titles = [m.name for m in matches]
    assert any("NFP" in t for t in titles)
    assert any("BOJ" in t for t in titles)
    assert not any("ECB" in t for t in titles)
    assert not any("Speech" in t for t in titles)
    # Sorted by absolute minutes_until
    assert abs(matches[0].minutes_until) <= abs(matches[-1].minutes_until)


def test_events_within_window_returns_empty_when_no_cache(tmp_path: Path):
    asof = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    matches = events_within_window(
        symbol="USDJPY=X", asof_utc=asof, cache_root=tmp_path
    )
    assert matches == []


def test_events_within_window_filters_by_impact(tmp_path: Path):
    asof = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    events = [
        EconomicEvent(
            title="Trivial", currency="USD", impact="LOW",
            starts_at_utc=asof + timedelta(minutes=10),
            forecast="", previous="",
        ),
    ]
    save_cached_calendar(events, cache_root=tmp_path)
    matches = events_within_window(
        symbol="USDJPY=X", asof_utc=asof,
        include_impacts=("HIGH", "MEDIUM"), cache_root=tmp_path,
    )
    assert matches == []
