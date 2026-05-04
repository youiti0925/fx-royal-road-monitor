from __future__ import annotations

from fx_monitor.ai.preflight import (
    AiPreviewPreflightResult,
    check_ai_authored_preview_preflight,
)


def test_preflight_fails_without_keys():
    result = check_ai_authored_preview_preflight({})
    assert result.ok is False
    assert "OPENAI_API_KEY_missing" in result.errors
    assert "ANTHROPIC_API_KEY_missing" in result.errors


def test_preflight_passes_with_both_keys_and_enabled():
    result = check_ai_authored_preview_preflight(
        {
            "OPENAI_API_KEY": "x",
            "ANTHROPIC_API_KEY": "y",
            "OPENAI_ENABLED": "true",
            "ANTHROPIC_ENABLED": "true",
        }
    )
    assert result.ok is True
    assert result.openai_ready is True
    assert result.claude_ready is True
    assert result.errors == []
    assert result.warnings == []


def test_preflight_warns_when_key_present_but_enabled_missing():
    result = check_ai_authored_preview_preflight(
        {
            "OPENAI_API_KEY": "x",
            "ANTHROPIC_API_KEY": "y",
            # no OPENAI_ENABLED / ANTHROPIC_ENABLED
        }
    )
    # Keys present so ok=True.
    assert result.ok is True
    # But warnings indicate the operator should set ENABLED explicitly.
    assert "OPENAI_ENABLED_not_true" in result.warnings
    assert "ANTHROPIC_ENABLED_not_true" in result.warnings


def test_preflight_partial_failure_when_only_one_key():
    result = check_ai_authored_preview_preflight(
        {
            "OPENAI_API_KEY": "x",
            "OPENAI_ENABLED": "true",
        }
    )
    assert result.ok is False
    assert result.openai_ready is True
    assert result.claude_ready is False
    assert "ANTHROPIC_API_KEY_missing" in result.errors


def test_preflight_to_dict_round_trip():
    result = check_ai_authored_preview_preflight({})
    d = result.to_dict()
    assert d["schema_version"] == "ai_preview_preflight_v1"
    assert d["ok"] is False
    assert "OPENAI_API_KEY_missing" in d["errors"]
    assert isinstance(result, AiPreviewPreflightResult)
