from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

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
from fx_monitor.postmortem.analyzer import analyze


def _entry(
    *,
    side: str,
    final_status: str,
    outcome_status: str,
    fav: float = 0.0,
    adv: float = 0.0,
    steps: list[tuple[str, str]] | None = None,
) -> CorpusEntry:
    asof = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
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
    proc_steps = [
        ProcedureStepSpec(key=k, label_ja=k, status=s, result_ja="")
        for k, s in (steps or [])
    ]
    spec = AiDecisionScreenSpec(
        provider="claude",
        symbol="EURUSD=X",
        timeframe="M5",
        side=side,  # type: ignore[arg-type]
        final_status=final_status,  # type: ignore[arg-type]
        procedure_steps=proc_steps,
    )
    return CorpusEntry(
        entry_id="test-1",
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


def _future(prices: list[tuple[float, float]]) -> list[Candle]:
    out = []
    base = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
    for i, (lo, hi) in enumerate(prices):
        out.append(
            Candle(
                t=base + timedelta(minutes=5 * (i + 1)),
                o=(lo + hi) / 2, h=hi, l=lo, c=(lo + hi) / 2, v=100.0,
            )
        )
    return out


def test_no_postmortem_for_pending():
    e = _entry(side="SELL", final_status="WAIT_BREAKOUT", outcome_status="PENDING")
    pm = analyze(e, [])
    assert pm.failure_mode == "outcome_pending"
    assert pm.severity == "low"


def test_no_postmortem_for_win():
    e = _entry(side="NEUTRAL", final_status="HOLD", outcome_status="WIN")
    pm = analyze(e, _future([(1.10, 1.10)]))
    assert pm.failure_mode == "no_post_mortem_needed"


def test_lose_directional_returns_stop_hit():
    e = _entry(
        side="SELL", final_status="WAIT_BREAKOUT", outcome_status="LOSE",
        fav=5.0, adv=35.0,
        steps=[("environment", "WAIT"), ("htf_dow", "WAIT"), ("wave_pattern", "PASS")],
    )
    pm = analyze(e, _future([(1.10, 1.105)]))
    assert pm.failure_mode == "stop_hit"
    assert pm.severity == "high"  # 35 >= 30
    # Suspicions should flag environment/htf_dow when those were WAIT/UNKNOWN
    keys = {s.step_key for s in pm.step_suspicions}
    assert "environment" in keys
    assert "htf_dow" in keys
    assert pm.countermeasures_ja  # non-empty


def test_neutral_missed_returns_moved_against_wait():
    e = _entry(
        side="BUY", final_status="WAIT_BREAKOUT", outcome_status="NEUTRAL_MISSED",
        fav=22.0, adv=-2.0,
        steps=[("breakout", "WAIT"), ("entry_price", "WAIT")],
    )
    pm = analyze(e, _future([(1.10, 1.105)]))
    assert pm.failure_mode == "moved_against_wait"
    assert pm.severity == "medium"
    keys = {s.step_key for s in pm.step_suspicions}
    assert "breakout" in keys


def test_lose_neutral_returns_moved_against_neutral():
    e = _entry(
        side="NEUTRAL", final_status="HOLD", outcome_status="LOSE",
        fav=40.0, adv=-5.0,
        steps=[("environment", "WAIT")],
    )
    pm = analyze(e, _future([(1.10, 1.110)]))
    assert pm.failure_mode == "moved_against_neutral"
    assert pm.severity == "high"


def test_facts_are_populated_when_future_present():
    e = _entry(
        side="SELL", final_status="WAIT_BREAKOUT", outcome_status="LOSE",
        fav=5.0, adv=20.0,
    )
    future = _future([(1.10, 1.11), (1.10, 1.12)])
    pm = analyze(e, future)
    assert pm.facts_ja
    assert any("最高値到達" in f for f in pm.facts_ja)
    assert any("最安値到達" in f for f in pm.facts_ja)
