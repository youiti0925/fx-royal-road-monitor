"""Mode-handling unit tests for fx_monitor.app.build_preview.

Tests the validation logic and the env-stripping rules directly,
without spinning up matplotlib or hitting the network.
"""

from __future__ import annotations

from fx_monitor.app.build_preview import (
    _ai_execution_state,
    _safe_env,
    _validate_ai_authored_specs,
)


def _populated_spec(provider: str) -> dict:
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
            {
                "id": "P1",
                "label": "P1",
                "role": "high",
                "index": 5,
                "price": 1.105,
            }
        ],
        "procedure_steps": [
            {
                "key": "wave_pattern",
                "label_ja": "波形",
                "status": "WAIT",
                "result_ja": "",
            }
        ],
    }


def _unknown_spec(provider: str, reason: str = "openai_disabled") -> dict:
    return {
        "schema_version": "ai_decision_screen_spec_v1",
        "provider": provider,
        "observation_only": True,
        "used_for_ready": False,
        "used_for_notification": False,
        "used_for_trading": False,
        "symbol": "EURUSD=X",
        "timeframe": "M5",
        "side": "NEUTRAL",
        "final_status": "UNKNOWN",
        "lines": [],
        "points": [],
        "zones": [],
        "procedure_steps": [],
        "problems": [reason],
    }


# ---------------------------------------------------------------------------
# _safe_env
# ---------------------------------------------------------------------------
def test_safe_local_strips_api_keys_and_disables_providers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "leaked-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "leaked-key")
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_ENABLED", "true")

    env = _safe_env("tests/fixtures/ohlc_preview_sample.csv", "out", mode="safe-local")
    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert env["OPENAI_ENABLED"] == "false"
    assert env["ANTHROPIC_ENABLED"] == "false"


def test_ai_authored_mode_keeps_keys_and_enables_providers(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-claude")
    monkeypatch.delenv("OPENAI_ENABLED", raising=False)
    monkeypatch.delenv("ANTHROPIC_ENABLED", raising=False)

    env = _safe_env(
        "tests/fixtures/ohlc_preview_sample.csv", "out", mode="ai-authored"
    )
    assert env["OPENAI_API_KEY"] == "test-key-openai"
    assert env["ANTHROPIC_API_KEY"] == "test-key-claude"
    # Default to true when key is present.
    assert env["OPENAI_ENABLED"] == "true"
    assert env["ANTHROPIC_ENABLED"] == "true"


# ---------------------------------------------------------------------------
# _validate_ai_authored_specs
# ---------------------------------------------------------------------------
def test_ai_authored_validation_passes_for_populated_specs():
    errors = _validate_ai_authored_specs(
        _populated_spec("openai"), _populated_spec("claude")
    )
    assert errors == []


def test_ai_authored_validation_rejects_unknown_specs():
    errors = _validate_ai_authored_specs(
        _unknown_spec("openai"), _unknown_spec("claude")
    )
    assert "openai_spec_unknown" in errors
    assert "claude_spec_unknown" in errors
    assert "openai_lines_empty" in errors
    assert "claude_points_empty" in errors


def test_ai_authored_validation_rejects_empty_lines_or_points():
    spec = _populated_spec("openai")
    spec["lines"] = []
    errors = _validate_ai_authored_specs(spec, _populated_spec("claude"))
    assert "openai_lines_empty" in errors
    assert "claude_lines_empty" not in errors


def test_ai_authored_validation_rejects_safety_flag_violations():
    bad_open = _populated_spec("openai")
    bad_open["used_for_ready"] = True
    bad_claude = _populated_spec("claude")
    bad_claude["used_for_trading"] = True
    errors = _validate_ai_authored_specs(bad_open, bad_claude)
    assert "openai_used_for_ready_not_false" in errors
    assert "claude_used_for_trading_not_false" in errors


# ---------------------------------------------------------------------------
# _ai_execution_state
# ---------------------------------------------------------------------------
def test_ai_execution_state_marks_unknown_as_not_executed():
    state = _ai_execution_state(
        _unknown_spec("openai", "openai_disabled"),
        _unknown_spec("claude", "anthropic_disabled"),
    )
    assert state["openai"]["executed"] is False
    assert state["claude"]["executed"] is False
    assert state["openai"]["not_run_reason"] == "openai_disabled"
    assert state["claude"]["not_run_reason"] == "anthropic_disabled"


def test_ai_execution_state_marks_populated_as_executed():
    state = _ai_execution_state(_populated_spec("openai"), _populated_spec("claude"))
    assert state["openai"]["executed"] is True
    assert state["claude"]["executed"] is True
    assert state["openai"]["lines"] == 1
    assert state["openai"]["points"] == 1
    assert state["openai"]["procedure_steps"] == 1
