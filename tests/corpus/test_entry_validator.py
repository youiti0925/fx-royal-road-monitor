"""Tests for ``entry_validator`` — every documented failure mode must be caught."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fx_monitor.ai.decision_screen_spec_schema import (
    AiDecisionScreenSpec,
    ProcedureStepSpec,
    ScreenLine,
    ScreenZone,
)
from fx_monitor.corpus.entry_validator import (
    CorpusValidationError,
    validate_entry,
)
from fx_monitor.corpus.schema import CorpusEntry, OutcomeLabel
from fx_monitor.live.market_pack_v2 import (
    AtrPack,
    MarketAnalysisPackV2,
    RangePack,
)


# ---- helpers ---------------------------------------------------------------


def _good_steps() -> list[ProcedureStepSpec]:
    """Produce a procedure_steps list covering all 29 knowledge_pack keys."""
    keys = [
        "fundamental_environment_check",
        "crisis_mode_detection",
        "intervention_zone_check",
        "verbal_intervention_scan",
        "htf_full_scan",
        "environment",
        "htf_dow",
        "htf_lines_check",
        "horizontal_levels",
        "trendline",
        "wave_pattern",
        "wave_lines",
        "fibonacci_zone",
        "buildup_check",
        "ma_alignment",
        "indicator_environment",
        "divergence_check",
        "stop_zone_estimation",
        "breakout",
        "retest_second_wave",
        "confirmation_candle",
        "mtf_alignment",
        "triple_confluence_count",
        "confluence_count",
        "entry_price",
        "stop_price",
        "target_price",
        "rr_check",
        "event_clear",
    ]
    return [
        ProcedureStepSpec(
            key=k,
            label_ja=f"ラベル {k}",
            status="PASS",
            result_ja=f"これは {k} に対する十分な長さのテキスト. doctrine 適用例.",
        )
        for k in keys
    ]


def _good_lines() -> list[ScreenLine]:
    return [
        ScreenLine(
            id="L_ENTRY",
            label="ENTRY",
            kind="neckline",
            role="entry_trigger",
            price=1.17400,
            confidence=0.7,
        ),
        ScreenLine(
            id="L_STOP",
            label="STOP",
            kind="invalidation",
            role="stop_reference",
            price=1.17500,
            confidence=0.7,
        ),
        ScreenLine(
            id="L_TARGET",
            label="TARGET",
            kind="target",
            role="target_reference",
            price=1.17200,
            confidence=0.6,
        ),
        ScreenLine(
            id="L_TL",
            label="TL",
            kind="trendline",
            role="dynamic_resistance",
            price=1.17400,
            start_index=10,
            start_price=1.17500,
            end_index=59,
            end_price=1.17400,
            confidence=0.5,
        ),
    ]


def _entry_with(
    *,
    steps: list[ProcedureStepSpec] | None = None,
    lines: list[ScreenLine] | None = None,
    zones: list[ScreenZone] | None = None,
    atr: float = 0.0002,  # 2 pip
) -> CorpusEntry:
    asof = datetime(2026, 5, 4, 13, 0, tzinfo=timezone.utc)
    pack = MarketAnalysisPackV2(
        symbol="EURUSD=X",
        asof_utc=asof,
        candles=[],
        pivots=[],
        atr=AtrPack(m5_14=atr),
        recent_range=RangePack(high_24h=1.18, low_24h=1.16),
        current_price=1.174,
        session="OVERLAP",
    )
    spec = AiDecisionScreenSpec(
        provider="claude",
        symbol="EURUSD=X",
        timeframe="M5",
        side="SELL",
        final_status="WAIT_RETEST",
        procedure_steps=steps if steps is not None else _good_steps(),
        lines=lines if lines is not None else _good_lines(),
        zones=zones if zones is not None else [],
    )
    return CorpusEntry(
        entry_id="t",
        asof_utc=asof,
        symbol="EURUSD=X",
        timeframe="M5",
        source="live_recorded",
        market_pack=pack,
        feature_vector=[1.0, 0.0, 0.0, 0.0],
        judgement=spec,
        judgement_at_utc=asof,
        outcome=OutcomeLabel(status="PENDING"),
    )


# ---- happy path ------------------------------------------------------------


def test_happy_path_returns_no_errors():
    assert validate_entry(_entry_with()) == []


# ---- F1: skeleton placeholders ---------------------------------------------


def test_f1_skeleton_in_result_ja_rejected():
    bad_steps = _good_steps()
    bad_steps[0] = bad_steps[0].model_copy(
        update={"result_ja": "WAIT - skeleton entry — full doctrine deferred"}
    )
    issues = validate_entry(_entry_with(steps=bad_steps))
    assert any("F1" in i and "placeholder" in i.lower() for i in issues), issues


def test_f1_too_short_result_ja_rejected():
    bad_steps = _good_steps()
    bad_steps[0] = bad_steps[0].model_copy(update={"result_ja": "短い"})
    issues = validate_entry(_entry_with(steps=bad_steps))
    assert any("F1" in i for i in issues), issues


def test_f1_label_ja_equal_to_key_rejected():
    bad_steps = _good_steps()
    bad_steps[0] = bad_steps[0].model_copy(update={"label_ja": bad_steps[0].key})
    issues = validate_entry(_entry_with(steps=bad_steps))
    assert any("F1" in i and "label_ja" in i for i in issues), issues


# ---- F4: doctrine coverage --------------------------------------------------


def test_f4_missing_step_keys_rejected():
    # Drop the first 3 steps — knowledge_pack expects all 29.
    bad_steps = _good_steps()[3:]
    issues = validate_entry(_entry_with(steps=bad_steps))
    assert any("F4" in i and "missing keys" in i for i in issues), issues


# ---- F5/F6: ENTRY-STOP gap --------------------------------------------------


def test_f5_too_tight_stop_rejected():
    # ATR 2pip × 0.5 = 1pip minimum gap. Set stop only 0.5pip from entry.
    bad_lines = _good_lines()
    bad_lines[1] = bad_lines[1].model_copy(update={"price": 1.17405})  # 0.5pip
    issues = validate_entry(_entry_with(lines=bad_lines))
    assert any("F5" in i and "ENTRY-STOP gap" in i for i in issues), issues


def test_f5_atr_appropriate_stop_accepted():
    # 5pip stop on ATR 2pip → 2.5×ATR → comfortably above 0.5×ATR threshold.
    lines = _good_lines()
    lines[1] = lines[1].model_copy(update={"price": 1.17450})
    assert validate_entry(_entry_with(lines=lines)) == []


# ---- F7: index range --------------------------------------------------------


def test_f7_zone_index_out_of_range_rejected():
    zones = [
        ScreenZone(
            id="Z1",
            label="bad zone",
            kind="buildup",
            price_low=1.17400,
            price_high=1.17500,
            index_low=615,  # absolute archive idx — must be local 0..120
            index_high=735,
        )
    ]
    issues = validate_entry(_entry_with(zones=zones))
    assert any("F7" in i and "Z1" in i for i in issues), issues


def test_f7_line_endpoint_out_of_range_rejected():
    lines = _good_lines()
    lines[3] = lines[3].model_copy(update={"end_index": 200})
    issues = validate_entry(_entry_with(lines=lines))
    assert any("F7" in i and "end_index" in i for i in issues), issues


# ---- F8: at least one slanted trendline -------------------------------------


def test_f8_no_slanted_trendline_rejected():
    # Strip the slanted line (last entry in _good_lines).
    lines = _good_lines()[:-1]
    issues = validate_entry(_entry_with(lines=lines))
    assert any("F8" in i for i in issues), issues


def test_f8_horizontal_only_trendline_rejected():
    # A line with kind=trendline but no start/end coords is just a horizontal.
    lines = _good_lines()
    lines[3] = lines[3].model_copy(
        update={"start_index": None, "end_index": None}
    )
    issues = validate_entry(_entry_with(lines=lines))
    assert any("F8" in i for i in issues), issues


# ---- F9: ENTRY/STOP/TARGET lines required -----------------------------------


def test_f9_missing_entry_rejected():
    lines = [l for l in _good_lines() if l.id != "L_ENTRY"]
    issues = validate_entry(_entry_with(lines=lines))
    assert any("F9" in i and "entry" in i.lower() for i in issues), issues


def test_f9_missing_stop_rejected():
    lines = [l for l in _good_lines() if l.id != "L_STOP"]
    issues = validate_entry(_entry_with(lines=lines))
    assert any("F9" in i and "invalidation" in i for i in issues), issues


def test_f9_missing_target_rejected():
    lines = [l for l in _good_lines() if l.id != "L_TARGET"]
    issues = validate_entry(_entry_with(lines=lines))
    assert any("F9" in i and "target" in i for i in issues), issues


# ---- store integration: bad entry raises -----------------------------------


def test_store_rejects_invalid_entry(tmp_path):
    from fx_monitor.corpus.store import JsonlVectorStore

    store = JsonlVectorStore(tmp_path)
    bad = _entry_with(
        steps=[
            ProcedureStepSpec(
                key="environment", label_ja="env", status="PASS",
                result_ja="x",  # too short → F1
            )
        ],
        lines=[],  # no entry/stop/target/trendline → F8/F9
    )
    with pytest.raises(CorpusValidationError) as excinfo:
        store.add(bad)
    assert "F1" in str(excinfo.value) or "F4" in str(excinfo.value)
    assert "F8" in str(excinfo.value)
    assert "F9" in str(excinfo.value)


def test_store_skip_validation_bypass(tmp_path):
    from fx_monitor.corpus.store import JsonlVectorStore

    store = JsonlVectorStore(tmp_path)
    bad = _entry_with(steps=[], lines=[])
    store.add(bad, skip_validation=True)
    assert len(store) == 1
