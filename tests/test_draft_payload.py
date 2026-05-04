from __future__ import annotations

from pathlib import Path

from fx_monitor.adapters import build_monitor_case_from_draft_payload
from fx_monitor.analysis.draft_payload import build_royal_road_draft_payload_from_snapshot
from fx_monitor.core.rule_engine import evaluate_monitor_case
from fx_monitor.data.csv_feed import load_ohlc_csv

FIXTURES = Path(__file__).parent / "fixtures"


def _draft():
    s = load_ohlc_csv(FIXTURES / "ohlc_sample.csv", symbol="EURUSD=X", timeframe="M5")
    return build_royal_road_draft_payload_from_snapshot(s)


def test_build_draft_payload_from_csv_snapshot_is_observation_only():
    draft = _draft()
    assert draft.observation_only is True
    assert draft.used_in_final_action is False
    assert draft.entry_plan["entry_status"] == "HOLD"
    assert draft.selected_entry_candidate["status"] == "HOLD"
    assert draft.royal_road_procedure_checklist["p0_pass"] is False


def test_draft_monitor_case_never_passes_rule_engine():
    case = build_monitor_case_from_draft_payload(_draft())
    result = evaluate_monitor_case(case)
    assert result.verdict in ("UNKNOWN", "WARN")
    assert result.verdict != "PASS"


def test_draft_monitor_case_with_injected_ready_status_is_warn():
    case = build_monitor_case_from_draft_payload(_draft())
    # Hostile: someone hand-edits the draft to claim READY. Rule engine
    # must still refuse and flag the violation.
    case.ai_payload["entry_plan"]["entry_status"] = "READY"
    result = evaluate_monitor_case(case)
    assert result.verdict == "WARN"
    assert any("forbidden" in r.lower() for r in result.reasons)


def test_draft_payload_carries_pivots_into_ai_payload():
    case = build_monitor_case_from_draft_payload(_draft())
    ai = case.ai_payload
    assert ai["observation_only"] is True
    assert ai["used_in_final_action"] is False
    assert "pivots" in ai
    assert "rough_support_resistance" in ai
    assert "rough_wave_context" in ai


def test_draft_payload_contains_rich_draft_but_still_not_ready():
    s = load_ohlc_csv(FIXTURES / "ohlc_sample.csv", symbol="EURUSD=X", timeframe="M5")
    draft = build_royal_road_draft_payload_from_snapshot(s)

    assert draft.rich_draft
    assert draft.rich_draft["observation_only"] is True
    assert draft.rich_draft["ready_eligible"] is False
    assert draft.entry_plan["entry_status"] == "HOLD"
    assert draft.royal_road_procedure_checklist["p0_pass"] is False
    # The rule engine still refuses to PASS on a draft.
    case = build_monitor_case_from_draft_payload(draft)
    assert evaluate_monitor_case(case).verdict in ("UNKNOWN", "WARN")


def test_draft_monitor_case_ai_payload_has_rich_draft_keys_only():
    s = load_ohlc_csv(FIXTURES / "ohlc_sample.csv", symbol="EURUSD=X", timeframe="M5")
    draft = build_royal_road_draft_payload_from_snapshot(s)
    case = build_monitor_case_from_draft_payload(draft)

    ai = case.ai_payload
    # Draft suffix keys must be present.
    for k in (
        "rich_draft",
        "pattern_levels_draft",
        "wave_derived_lines_draft",
        "structural_lines_draft",
        "support_resistance_v2_draft",
        "trendline_context_draft",
        "royal_road_procedure_checklist_draft",
    ):
        assert k in ai

    # Production-named keys must not leak in from the draft path.
    for k in (
        "pattern_levels",
        "wave_derived_lines",
        "structural_lines",
        "support_resistance_v2",
        "trendline_context",
    ):
        assert k not in ai
