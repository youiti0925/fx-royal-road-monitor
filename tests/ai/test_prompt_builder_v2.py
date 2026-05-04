from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fx_monitor.ai.decision_screen_spec_schema import AiDecisionScreenSpec
from fx_monitor.ai.prompt_builder_v2 import (
    DEFAULT_KNOWLEDGE_PACK_PATH,
    SYSTEM_PROMPT,
    build_decision_prompt,
    load_knowledge_pack,
)
from fx_monitor.corpus.schema import CorpusEntry, OutcomeLabel
from fx_monitor.live.candle import Candle
from fx_monitor.live.market_pack_v2 import (
    AtrPack,
    CalendarEvent,
    MarketAnalysisPackV2,
    RangePack,
)
from fx_monitor.live.pivots_v2 import PivotPointV2


def _pack(**overrides) -> MarketAnalysisPackV2:
    base = dict(
        symbol="EURUSD=X",
        asof_utc=datetime(2026, 5, 4, 13, 0, tzinfo=timezone.utc),
        candles=[
            Candle(
                t=datetime.fromtimestamp(i * 300, tz=timezone.utc),
                o=1.10 + 0.001 * i,
                h=1.105 + 0.001 * i,
                l=1.095 + 0.001 * i,
                c=1.10 + 0.001 * i,
                v=100.0,
            )
            for i in range(60)
        ],
        pivots=[
            PivotPointV2(
                index=20,
                timestamp_utc=datetime.fromtimestamp(20 * 300, tz=timezone.utc).isoformat(),
                price=1.115,
                kind="HIGH",
                scale="swing",
                strength=10,
            )
        ],
        atr=AtrPack(m5_14=0.001, h1_14=0.002, h4_14=0.004),
        recent_range=RangePack(high_24h=1.20, low_24h=1.09),
        current_price=1.16,
        session="OVERLAP",
    )
    base.update(overrides)
    return MarketAnalysisPackV2(**base)


def _entry(asof: datetime, *, side: str, fs: str, outcome: str) -> CorpusEntry:
    pack = _pack(asof_utc=asof)
    spec = AiDecisionScreenSpec(
        provider="claude",
        symbol=pack.symbol,
        timeframe="M5",
        side=side,  # type: ignore[arg-type]
        final_status=fs,  # type: ignore[arg-type]
    )
    return CorpusEntry(
        entry_id=f"e-{asof.isoformat()}",
        asof_utc=asof,
        symbol=pack.symbol,
        timeframe="M5",
        source="live_recorded",
        market_pack=pack,
        feature_vector=[0.0] * 8,
        judgement=spec,
        judgement_at_utc=asof,
        outcome=OutcomeLabel(  # type: ignore[arg-type]
            status=outcome,
            max_favorable_pip=10.0,
            max_adverse_pip=-5.0,
            bars_observed=60,
            filled_at_utc=asof,
        ),
    )


def test_default_knowledge_pack_loads_and_has_required_sections():
    kp = load_knowledge_pack()
    assert kp["schema_version"] == "knowledge_pack_v2"
    assert "glossary" in kp
    assert "procedure_steps" in kp
    assert len(kp["procedure_steps"]) >= 14
    assert "few_shot_examples" in kp


def test_system_prompt_pins_safety_contract():
    for token in [
        "observation_only=true",
        "used_for_ready=false",
        "used_for_notification=false",
        "used_for_trading=false",
        "READY通知/自動売買/手動売買連動はすべて永久禁止",
    ]:
        assert token in SYSTEM_PROMPT


def test_user_prompt_includes_numeric_facts():
    pack = _pack()
    p = build_decision_prompt(pack, retrieved=[])
    for token in [
        "symbol: EURUSD=X",
        "timeframe: M5",
        "session: OVERLAP",
        "ATR: m5_14=",
        "## ローソク足",
        "## 多スケールピボット",
    ]:
        assert token in p.user


def test_user_prompt_excludes_pollution_keys():
    """The v2 prompt must not mention any code-derived judgement label."""
    pack = _pack()
    p = build_decision_prompt(pack, retrieved=[])
    for forbidden in [
        "pattern_kind",
        "wave_derived_lines_draft",
        "structural_lines_draft",
        "trendline_context_draft",
        "royal_road_procedure_checklist_draft",
        "possible_double_top",
    ]:
        assert forbidden not in p.user


def test_user_prompt_lists_glossary_and_14_steps():
    pack = _pack()
    p = build_decision_prompt(pack, retrieved=[])
    assert "## 用語定義" in p.user
    assert "## 王道14手順" in p.user
    # 14手順のキー名が全部現れること
    for key in [
        "environment",
        "htf_dow",
        "horizontal_levels",
        "trendline",
        "wave_pattern",
        "wave_lines",
        "breakout",
        "retest",
        "confirmation_candle",
        "entry_price",
        "stop_price",
        "target_price",
        "rr_check",
        "event_clear",
    ]:
        assert key in p.user


def test_cold_start_renders_explicit_hint():
    pack = _pack()
    p = build_decision_prompt(pack, retrieved=[])
    assert "cold start" in p.user


def test_retrieved_cases_render_with_outcome_aggregate():
    pack = _pack()
    retrieved = [
        (0.95, _entry(datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc), side="SELL", fs="WAIT_BREAKOUT", outcome="WIN")),
        (0.91, _entry(datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc), side="SELL", fs="WAIT_BREAKOUT", outcome="LOSE")),
        (0.88, _entry(datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc), side="SELL", fs="WAIT_RETEST", outcome="NEUTRAL_GOOD")),
    ]
    p = build_decision_prompt(pack, retrieved=retrieved)
    assert "ケース1" in p.user
    assert "類似度 0.95" in p.user
    assert "WIN" in p.user
    assert "LOSE" in p.user
    assert "集計" in p.user


def test_calendar_events_rendered():
    pack = _pack(
        calendar_events_within_60min=[CalendarEvent(name="NFP", impact="HIGH", minutes_until=20)]
    )
    p = build_decision_prompt(pack, retrieved=[])
    assert "NFP" in p.user
    assert "HIGH" in p.user


def test_pack_path_returned_for_audit():
    pack = _pack()
    p = build_decision_prompt(pack, retrieved=[])
    assert Path(p.knowledge_pack_path).name == "knowledge_pack_v2.json"
