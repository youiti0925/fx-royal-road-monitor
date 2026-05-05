from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fx_monitor.ai.decision_screen_spec_schema import (
    AiDecisionScreenSpec,
    ProcedureStepSpec,
)
from fx_monitor.corpus.schema import CorpusEntry, OutcomeLabel
from fx_monitor.live.candle import Candle
from fx_monitor.live.market_pack_v2 import (
    AtrPack,
    MarketAnalysisPackV2,
    RangePack,
)
from fx_monitor.postmortem.learning_journal import build_learning_journal


def _entry(
    eid: str,
    *,
    asof: datetime,
    side: str,
    final_status: str,
    outcome_status: str,
    fav: float = 0.0,
    adv: float = 0.0,
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
        procedure_steps=[
            ProcedureStepSpec(key="environment", label_ja="env", status="WAIT", result_ja=""),
        ],
    )
    return CorpusEntry(
        entry_id=eid,
        asof_utc=asof,
        symbol="EURUSD=X",
        timeframe="M5",
        source="live_recorded",
        market_pack=pack,
        feature_vector=[0.0] * 8,
        judgement=spec,
        judgement_at_utc=asof,
        outcome=OutcomeLabel(  # type: ignore[arg-type]
            status=outcome_status,
            max_favorable_pip=fav,
            max_adverse_pip=adv,
            bars_observed=60,
        ),
    )


def _stub_fetcher(symbol, asof, n):
    base_t = asof + timedelta(minutes=5)
    return [
        Candle(t=base_t + timedelta(minutes=5 * i),
               o=1.10, h=1.11, l=1.10, c=1.105, v=100.0)
        for i in range(n)
    ]


def test_journal_aggregates_actionable_only():
    now = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    entries = [
        _entry("a", asof=now - timedelta(days=2), side="SELL",
               final_status="WAIT_BREAKOUT", outcome_status="LOSE",
               fav=5.0, adv=30.0),
        _entry("b", asof=now - timedelta(days=3), side="NEUTRAL",
               final_status="HOLD", outcome_status="WIN"),
        _entry("c", asof=now - timedelta(days=5), side="BUY",
               final_status="WAIT_BREAKOUT", outcome_status="NEUTRAL_MISSED",
               fav=20.0, adv=-2.0),
        # Out of window
        _entry("z", asof=now - timedelta(days=60), side="SELL",
               final_status="WAIT_BREAKOUT", outcome_status="LOSE",
               fav=5.0, adv=30.0),
    ]

    journal = build_learning_journal(
        entries, fetch_future=_stub_fetcher, window_days=30, now_utc=now,
    )
    assert journal.total_examined == 3
    # Only LOSE and NEUTRAL_MISSED produce actionable entries.
    assert len(journal.actionable_entries) == 2
    ids = {ae.entry_id for ae in journal.actionable_entries}
    assert ids == {"a", "c"}
    # Failure mode counter has both modes.
    assert "stop_hit" in journal.failure_mode_counts
    assert "moved_against_wait" in journal.failure_mode_counts
    # Countermeasures are non-empty for those modes.
    assert journal.countermeasure_frequency
