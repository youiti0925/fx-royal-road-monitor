from __future__ import annotations

import json
from pathlib import Path

import pytest

from fx_monitor.adapters import build_monitor_case_from_royal_road_payload

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_ready_sell_payload_converts_to_monitor_case():
    raw = _load("royal_road_ready_sell_payload.json")
    case = build_monitor_case_from_royal_road_payload(raw)

    assert case.chart_payload.symbol == "EURUSD=X"
    assert case.chart_payload.timeframe == "M5"
    assert case.chart_payload.trigger.occurred is True
    assert case.chart_payload.trigger.type == "retest"
    assert case.chart_payload.calendar.high_impact_within_15min is False

    ai = case.ai_payload
    assert ai["entry_plan"]["entry_status"] == "READY"
    assert ai["selected_entry_candidate"]["status"] == "READY"
    assert ai["royal_road_procedure_checklist"]["p0_pass"] is True
    assert "structural_lines" in ai
    assert "pattern_levels" in ai
    assert "wave_derived_lines" in ai
    assert ai["source"] == "existing_royal_road_payload"
    assert case.source_payload == raw


def test_wait_retest_payload_converts_to_breakout_trigger_state():
    raw = _load("royal_road_wait_retest_payload.json")
    case = build_monitor_case_from_royal_road_payload(raw)

    assert case.chart_payload.trigger.occurred is True
    assert case.chart_payload.trigger.type == "breakout"
    assert case.ai_payload["entry_plan"]["entry_status"] == "WAIT_RETEST"


def test_event_block_payload_sets_calendar_guard():
    raw = _load("royal_road_event_block_payload.json")
    case = build_monitor_case_from_royal_road_payload(raw)

    assert case.chart_payload.calendar.high_impact_within_15min is True
    assert case.ai_payload["fundamental_sidebar"]["event_risk_status"] == "BLOCK"


def test_adapter_rejects_non_dict():
    with pytest.raises(TypeError):
        build_monitor_case_from_royal_road_payload([1, 2, 3])  # type: ignore[arg-type]


def test_adapter_chart_image_path_passes_through():
    raw = _load("royal_road_ready_sell_payload.json")
    case = build_monitor_case_from_royal_road_payload(raw, chart_image_path="/tmp/x.png")
    assert case.chart_image_path == "/tmp/x.png"
    assert case.ai_payload["chart_image_path"] == "/tmp/x.png"
