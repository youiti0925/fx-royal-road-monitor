from __future__ import annotations

from fx_monitor.ai.decision_screen_spec_compare import (
    SCHEMA_VERSION,
    compare_decision_screen_specs,
)


def _spec(provider: str, **overrides):
    base = {
        "schema_version": "ai_decision_screen_spec_v1",
        "provider": provider,
        "observation_only": True,
        "used_for_ready": False,
        "used_for_notification": False,
        "used_for_trading": False,
        "symbol": "EURUSD=X",
        "timeframe": "M5",
        "side": "SELL",
        "final_status": "WAIT_BREAKOUT",
        "lines": [],
        "points": [],
        "zones": [],
        "procedure_steps": [],
    }
    base.update(overrides)
    return base


def test_compare_safety_flags_pinned():
    o = _spec("openai")
    c = _spec("claude")
    result = compare_decision_screen_specs(openai_spec=o, claude_spec=c)
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["observation_only"] is True
    assert result["used_for_ready"] is False
    assert result["used_for_notification"] is False
    assert result["used_for_trading"] is False


def test_compare_agree_when_all_match():
    line = {
        "id": "L1",
        "label": "WNL",
        "kind": "neckline",
        "role": "entry_trigger",
        "price": 1.1000,
        "anchor_points": ["NL"],
    }
    o = _spec("openai", lines=[{**line, "id": "OL1"}])
    c = _spec("claude", lines=[{**line, "id": "CL1"}])
    result = compare_decision_screen_specs(openai_spec=o, claude_spec=c)
    assert result["agreement"] == "AGREE"
    assert len(result["matched_lines"]) == 1
    assert result["matched_lines"][0]["openai_id"] == "OL1"
    assert result["matched_lines"][0]["claude_id"] == "CL1"


def test_compare_openai_only_and_claude_only():
    o = _spec(
        "openai",
        lines=[
            {
                "id": "OL1",
                "label": "WNL",
                "kind": "neckline",
                "role": "entry_trigger",
                "price": 1.1,
                "anchor_points": ["NL"],
            }
        ],
    )
    c = _spec(
        "claude",
        lines=[
            {
                "id": "CL1",
                "label": "STL",
                "kind": "trendline",
                "role": "top_structure",
                "start_index": 1,
                "start_price": 1.10,
                "end_index": 5,
                "end_price": 1.11,
                "anchor_points": ["P1", "P2"],
            }
        ],
    )
    result = compare_decision_screen_specs(openai_spec=o, claude_spec=c)
    assert any(line["id"] == "OL1" for line in result["openai_only"])
    assert any(line["id"] == "CL1" for line in result["claude_only"])
    assert result["agreement"] in ("PARTIAL", "DISAGREE")


def test_compare_price_conflict_recorded():
    o = _spec(
        "openai",
        lines=[
            {
                "id": "OL1",
                "label": "WNL",
                "kind": "neckline",
                "role": "entry_trigger",
                "price": 1.1000,
                "anchor_points": ["NL"],
            }
        ],
    )
    c = _spec(
        "claude",
        lines=[
            {
                "id": "CL1",
                "label": "WNL",
                "kind": "neckline",
                "role": "entry_trigger",
                "price": 1.2000,  # 9 % apart -> conflict
                "anchor_points": ["NL"],
            }
        ],
    )
    result = compare_decision_screen_specs(openai_spec=o, claude_spec=c)
    assert any(c["openai_id"] == "OL1" for c in result["conflicts"])


def test_compare_unknown_when_either_spec_unknown():
    o = _spec("openai", final_status="UNKNOWN")
    c = _spec("claude")
    result = compare_decision_screen_specs(openai_spec=o, claude_spec=c)
    assert result["agreement"] == "UNKNOWN"


def test_compare_step_disagreements_reported():
    o = _spec(
        "openai",
        procedure_steps=[
            {"key": "wave_pattern", "label_ja": "波形", "status": "WAIT", "result_ja": ""},
        ],
    )
    c = _spec(
        "claude",
        procedure_steps=[
            {"key": "wave_pattern", "label_ja": "波形", "status": "UNKNOWN", "result_ja": ""},
        ],
    )
    result = compare_decision_screen_specs(openai_spec=o, claude_spec=c)
    assert result["step_disagreements"]
    assert result["step_disagreements"][0]["step"] == "wave_pattern"
