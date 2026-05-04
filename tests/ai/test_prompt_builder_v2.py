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


def test_user_prompt_lists_glossary_and_procedure_steps():
    pack = _pack()
    p = build_decision_prompt(pack, retrieved=[])
    assert "## 用語定義" in p.user
    # The procedure title is auto-numbered from the knowledge pack length,
    # so just match the prefix and let the count grow.
    assert "## 王道" in p.user and "手順" in p.user
    # The original 14 step keys must all still be present.
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


def test_user_prompt_includes_v3_principles():
    """The v3 doctrine adds higher-order principles: layered analysis,
    indicator-environment filter, MTF, confluence axes, invalidation,
    and the pre-trade checklist. They must reach the AI."""
    pack = _pack()
    p = build_decision_prompt(pack, retrieved=[])
    for token in [
        "## 王道判定の上位原則",
        "階層分析",
        "指標は環境に応じて使い分ける",
        "MTF",
        "コンフルエンス 5軸",
        "損切り",
        "インバリデーション",
        "自己診断",
    ]:
        assert token in p.user, f"missing principle marker: {token!r}"


def test_user_prompt_includes_v4_top_principles():
    """v4 doctrine: HTF supremacy must be the FIRST principle, plus
    Triple Confluence / Fibonacci zone / Breakout 3-signs / line filter
    / 3-layer psychology must all reach the AI."""
    pack = _pack()
    p = build_decision_prompt(pack, retrieved=[])
    for token in [
        "【最上位原則】上位足の絶対的優位性",
        "HTF Supremacy",
        "トリプル根拠",
        "Triple Confluence",
        "フィボナッチ・ゾーン doctrine",
        "プライム",
        "高勝率ブレイクアウトの3サイン",
        "ビルドアップ4段階",
        "ライン重要度4フィルター",
        "反転の3独立動機",
        "3層思考",
    ]:
        assert token in p.user, f"missing v4 marker: {token!r}"


def test_htf_supremacy_appears_before_other_principles():
    """HTF must be the FIRST section under 上位原則 — explicit ordering.

    We search for the specific section headers (### prefix) so the test
    is not confused by the glossary mentioning the same term earlier.
    """
    pack = _pack()
    p = build_decision_prompt(pack, retrieved=[])
    user = p.user
    htf_idx = user.find("### 【最上位原則】上位足の絶対的優位性")
    triple_idx = user.find("### トリプル根拠")
    layered_idx = user.find("### 階層分析")
    mtf_idx = user.find("### MTF (マルチタイムフレーム) 原則")
    assert htf_idx > 0, "HTF supremacy section header missing"
    assert triple_idx > htf_idx, "HTF must precede triple confluence section"
    assert layered_idx > htf_idx, "HTF must precede layered analysis section"
    assert mtf_idx > htf_idx, "HTF must precede MTF principle section"


def test_v4_glossary_includes_new_terms():
    """v4 added Stop Hunt Zone, Fibonacci, Build-up, etc."""
    from fx_monitor.ai.prompt_builder_v2 import load_knowledge_pack

    kp = load_knowledge_pack()
    glossary = kp["glossary"]
    for term in [
        "ビルドアップ (Build-up)",
        "ビルドアップ4段階",
        "火薬庫 (Stop Hunt Zone)",
        "損切り連鎖加速 (Stop Cascade)",
        "3層思考 (事実→心理→予測)",
        "フィボナッチ・リトレースメント",
        "黄金比 61.8%",
        "プライム・エントリーゾーン (50-61.8%)",
        "ライン重要度4フィルター",
        "キリ番 (Round Number)",
        "ライン賞味期限 (Line Expiration)",
        "トリプル根拠 (Triple Confluence)",
        "MTF (Multi-Timeframe) 階層",
    ]:
        assert term in glossary, f"missing v4 glossary term: {term!r}"


def test_v4_doctrine_version_marker():
    """The pack carries an explicit v4 doctrine_version marker."""
    from fx_monitor.ai.prompt_builder_v2 import load_knowledge_pack

    kp = load_knowledge_pack()
    assert kp.get("doctrine_version", "").startswith("v4_"), (
        f"doctrine_version should start with 'v4_', got {kp.get('doctrine_version')!r}"
    )


def test_v4_procedure_steps_include_htf_full_scan_first():
    """HTF full scan must appear FIRST in the procedure steps list."""
    from fx_monitor.ai.prompt_builder_v2 import load_knowledge_pack

    kp = load_knowledge_pack()
    steps = kp["procedure_steps"]
    assert steps[0]["key"] == "htf_full_scan", (
        f"first step must be htf_full_scan, got {steps[0]['key']!r}"
    )


def test_v4_procedure_steps_include_new_v4_keys():
    """Phase 9 (v4) added several new step keys."""
    from fx_monitor.ai.prompt_builder_v2 import load_knowledge_pack

    kp = load_knowledge_pack()
    keys = {s["key"] for s in kp["procedure_steps"]}
    for key in [
        "htf_full_scan",
        "htf_lines_check",
        "fibonacci_zone",
        "buildup_check",
        "stop_zone_estimation",
        "retest_second_wave",
        "triple_confluence_count",
    ]:
        assert key in keys, f"missing v4 procedure step: {key!r}"


def test_user_prompt_includes_new_procedure_keys():
    """Phase 9 added MTF, confluence, MA-alignment and indicator-env steps."""
    pack = _pack()
    p = build_decision_prompt(pack, retrieved=[])
    for key in [
        "ma_alignment",
        "indicator_environment",
        "divergence_check",
        "mtf_alignment",
        "confluence_count",
    ]:
        assert key in p.user, f"missing procedure step key: {key!r}"


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
