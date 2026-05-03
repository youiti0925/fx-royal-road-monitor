from __future__ import annotations

import json
from pathlib import Path

from fx_monitor.adapters import build_monitor_case_from_royal_road_payload
from fx_monitor.core.rule_engine import evaluate_monitor_case

FIXTURES = Path(__file__).parent / "fixtures"


def _case(name: str):
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return build_monitor_case_from_royal_road_payload(raw)


def test_ready_sell_monitor_case_passes_rule_engine():
    result = evaluate_monitor_case(_case("royal_road_ready_sell_payload.json"))
    assert result.verdict == "PASS"
    assert result.bias == "short"


def test_wait_retest_monitor_case_does_not_pass():
    result = evaluate_monitor_case(_case("royal_road_wait_retest_payload.json"))
    assert result.verdict in ("WAIT", "WARN")
    assert result.verdict != "PASS"


def test_event_block_monitor_case_blocks():
    result = evaluate_monitor_case(_case("royal_road_event_block_payload.json"))
    assert result.verdict == "BLOCK"
    assert result.bias == "none"


def test_ready_status_but_p0_false_does_not_pass():
    case = _case("royal_road_ready_sell_payload.json")
    case.ai_payload["royal_road_procedure_checklist"]["p0_pass"] = False
    result = evaluate_monitor_case(case)
    assert result.verdict == "WARN"


def test_ready_with_low_rr_does_not_pass():
    case = _case("royal_road_ready_sell_payload.json")
    case.ai_payload["entry_plan"]["rr"] = 1.5
    result = evaluate_monitor_case(case)
    assert result.verdict == "WARN"
    assert any("RR" in r for r in result.reasons)


def test_ready_with_invalid_sell_price_order_does_not_pass():
    case = _case("royal_road_ready_sell_payload.json")
    # SELL needs target < entry < stop. Make target > entry.
    case.ai_payload["entry_plan"]["target_price"] = 1.2000
    result = evaluate_monitor_case(case)
    assert result.verdict == "WARN"


def test_ready_with_confirmation_candle_step_wait_does_not_pass():
    case = _case("royal_road_ready_sell_payload.json")
    for step in case.ai_payload["royal_road_procedure_checklist"]["steps"]:
        if step["key"] == "confirmation_candle":
            step["status"] = "WAIT"
    result = evaluate_monitor_case(case)
    assert result.verdict == "WARN"
