from __future__ import annotations

from fx_monitor.ai.decision_screen_prompt_builder import (
    build_decision_screen_repair_prompt,
)
from fx_monitor.ai.decision_screen_spec_schema import (
    validate_decision_screen_spec_for_user_preview,
)


def _populated_spec(provider: str = "openai") -> dict:
    return {
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
        "lines": [
            {
                "id": "L1",
                "label": "WNL",
                "kind": "neckline",
                "role": "entry_trigger",
                "price": 1.10,
                "anchor_points": ["NL"],
            }
        ],
        "points": [
            {"id": "P1", "label": "P1", "role": "high",
             "index": 5, "price": 1.105}
        ],
        "procedure_steps": [
            {"key": "wave_pattern", "label_ja": "波形",
             "status": "WAIT", "result_ja": ""}
        ],
    }


# ---------------------------------------------------------------------------
# validate_decision_screen_spec_for_user_preview
# ---------------------------------------------------------------------------
def test_validator_accepts_populated_spec():
    errors = validate_decision_screen_spec_for_user_preview(
        _populated_spec("openai"), "openai"
    )
    assert errors == []


def test_validator_flags_unknown_final_status():
    spec = _populated_spec("openai")
    spec["final_status"] = "UNKNOWN"
    errors = validate_decision_screen_spec_for_user_preview(spec, "openai")
    assert "openai_final_status_unknown" in errors


def test_validator_flags_empty_lines_points_steps():
    spec = _populated_spec("claude")
    spec["lines"] = []
    spec["points"] = []
    spec["procedure_steps"] = []
    errors = validate_decision_screen_spec_for_user_preview(spec, "claude")
    assert "claude_lines_empty" in errors
    assert "claude_points_empty" in errors
    assert "claude_procedure_steps_empty" in errors


def test_validator_flags_safety_violations():
    spec = _populated_spec("openai")
    spec["used_for_ready"] = True
    spec["used_for_notification"] = True
    spec["used_for_trading"] = True
    spec["observation_only"] = False
    errors = validate_decision_screen_spec_for_user_preview(spec, "openai")
    assert "openai_used_for_ready_not_false" in errors
    assert "openai_used_for_notification_not_false" in errors
    assert "openai_used_for_trading_not_false" in errors
    assert "openai_observation_only_not_true" in errors


def test_validator_handles_non_dict():
    errors = validate_decision_screen_spec_for_user_preview([], "openai")
    assert errors == ["openai_spec_not_dict"]


# ---------------------------------------------------------------------------
# build_decision_screen_repair_prompt
# ---------------------------------------------------------------------------
def test_repair_prompt_contains_validation_errors_and_previous_spec():
    pack = {"symbol": "EURUSD=X", "timeframe": "M5"}
    prev = _populated_spec("openai")
    errors = ["openai_lines_empty", "openai_points_empty"]
    prompt = build_decision_screen_repair_prompt(
        market_analysis_pack=pack,
        previous_spec=prev,
        validation_errors=errors,
        provider="openai",
    )
    user = prompt.user
    assert "openai_lines_empty" in user
    assert "openai_points_empty" in user
    assert "ai_decision_screen_spec_v1" in user
    assert "EURUSD=X" in user
    assert "points を空にしない" in user
    assert "lines を空にしない" in user
    assert "procedure_steps を空にしない" in user
    assert 'provider = "openai"' in user


def test_repair_prompt_system_keeps_safety_contract():
    pack = {"symbol": "EURUSD=X", "timeframe": "M5"}
    prev = _populated_spec("claude")
    errors = ["claude_final_status_unknown"]
    prompt = build_decision_screen_repair_prompt(
        market_analysis_pack=pack,
        previous_spec=prev,
        validation_errors=errors,
        provider="claude",
    )
    sysmsg = prompt.system
    assert "用ではありません" in sysmsg or "観測専用" in sysmsg
    assert "used_for_ready=false" in sysmsg
    assert "used_for_notification=false" in sysmsg
    assert "used_for_trading=false" in sysmsg
    assert "observation_only=true" in sysmsg
