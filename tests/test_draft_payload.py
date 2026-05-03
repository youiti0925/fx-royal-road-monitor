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
