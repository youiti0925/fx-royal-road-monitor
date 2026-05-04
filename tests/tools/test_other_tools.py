from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fx_monitor.ai.decision_screen_spec_schema import AiDecisionScreenSpec
from fx_monitor.corpus.schema import CorpusEntry, OutcomeLabel
from fx_monitor.corpus.store import JsonlVectorStore
from fx_monitor.live.candle import Candle
from fx_monitor.live.market_pack_v2 import (
    AtrPack,
    MarketAnalysisPackV2,
    RangePack,
)
from fx_monitor.tools._paths import corpus_root
from fx_monitor.tools.flag_dissent import flag_dissent
from fx_monitor.tools.monthly_report import build_report
from fx_monitor.tools.update_outcomes import update_outcomes


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FX_MONITOR_ROOT", str(tmp_path))


def _make_entry(
    entry_id: str,
    *,
    asof: datetime,
    outcome_status: str = "PENDING",
    final_status: str = "WAIT_BREAKOUT",
    side: str = "SELL",
) -> CorpusEntry:
    pack = MarketAnalysisPackV2(
        symbol="EURUSD=X",
        asof_utc=asof,
        candles=[],
        pivots=[],
        atr=AtrPack(m5_14=0.001),
        recent_range=RangePack(high_24h=1.20, low_24h=1.09),
        current_price=1.10,
        session="OVERLAP",
    )
    spec = AiDecisionScreenSpec(
        provider="claude",
        symbol="EURUSD=X",
        timeframe="M5",
        side=side,  # type: ignore[arg-type]
        final_status=final_status,  # type: ignore[arg-type]
    )
    return CorpusEntry(
        entry_id=entry_id,
        asof_utc=asof,
        symbol="EURUSD=X",
        timeframe="M5",
        source="live_recorded",
        market_pack=pack,
        feature_vector=[0.0] * 8,
        judgement=spec,
        judgement_at_utc=asof,
        outcome=OutcomeLabel(status=outcome_status),  # type: ignore[arg-type]
    )


def test_flag_dissent_marks_existing_entry():
    store = JsonlVectorStore(corpus_root("default"))
    asof = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
    store.add(_make_entry("e1", asof=asof, outcome_status="WIN"))

    info = flag_dissent(entry_id="e1", note="上位足と矛盾")
    assert info["ok"] is True

    s2 = JsonlVectorStore(corpus_root("default"))
    e = s2.get("e1")
    assert e is not None and e.user_dissent is True
    assert e.user_dissent_note == "上位足と矛盾"


def test_flag_dissent_returns_false_for_unknown_id():
    JsonlVectorStore(corpus_root("default"))  # ensure store initialised
    info = flag_dissent(entry_id="missing")
    assert info["ok"] is False


def test_update_outcomes_uses_injected_fetcher():
    store = JsonlVectorStore(corpus_root("default"))
    now = datetime(2026, 5, 4, 18, 0, tzinfo=timezone.utc)
    asof = now - timedelta(hours=10)
    store.add(_make_entry("p1", asof=asof, outcome_status="PENDING"))

    def stub_fetcher(symbol: str, asof_arg: datetime, n: int) -> list[Candle]:
        return [
            Candle(
                t=asof_arg + timedelta(minutes=5 * (i + 1)),
                o=1.09995 - 0.0001 * i,
                h=1.10000 - 0.0001 * i,
                l=1.09950 - 0.0001 * i,
                c=1.09975 - 0.0001 * i,
                v=100.0,
            )
            for i in range(n)
        ]

    info = update_outcomes(fetch_future=stub_fetcher, lookahead_bars=60, now_utc=now)
    assert info["filled"] == 1


def test_monthly_report_aggregates_recent_entries():
    store = JsonlVectorStore(corpus_root("default"))
    now = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
    store.add(_make_entry("a", asof=now - timedelta(days=2), outcome_status="WIN"))
    store.add(_make_entry("b", asof=now - timedelta(days=5), outcome_status="LOSE"))
    store.add(_make_entry("c", asof=now - timedelta(days=40), outcome_status="WIN"))  # outside window

    report = build_report(days=30, now_utc=now)
    assert report["total_entries_in_window"] == 2
    assert report["total_corpus_size"] == 3
    assert report["outcome_counts"].get("WIN") == 1
    assert report["outcome_counts"].get("LOSE") == 1
    assert report["win_rate_among_scored"] == pytest.approx(0.5)


def test_monthly_report_handles_empty_window():
    JsonlVectorStore(corpus_root("default"))  # initialise
    report = build_report(days=30, now_utc=datetime(2026, 5, 4, tzinfo=timezone.utc))
    assert report["total_entries_in_window"] == 0
    assert report["win_rate_among_scored"] is None
