from __future__ import annotations

from fx_monitor.ai.decision_screen_spec_schema import (
    AiDecisionScreenSpec,
    decision_screen_spec_schema_as_dict,
    parse_decision_screen_spec,
    safe_unknown_spec,
)


def _good_payload() -> dict:
    return {
        "schema_version": "ai_decision_screen_spec_v1",
        "provider": "openai",
        "symbol": "EURUSD=X",
        "timeframe": "M5",
        "side": "SELL",
        "final_status": "WAIT_BREAKOUT",
        "pattern_label_ja": "ダブルトップ候補",
        "market_story_ja": "上昇後にネックライン付近で揉み合い",
        "lines": [
            {
                "id": "L1",
                "label": "WNL",
                "kind": "neckline",
                "role": "entry_trigger",
                "price": 1.1000,
                "anchor_points": ["NL"],
                "confidence": 0.6,
                "reason_ja": "P1とP2の中間にNLが集中",
            }
        ],
        "summary_ja": "観測専用の例",
    }


def test_schema_top_level_required_fields():
    schema = decision_screen_spec_schema_as_dict()
    required = set(schema.get("required", []))
    # Pydantic marks fields without defaults as required. provider,
    # symbol, and timeframe have no defaults; schema_version /
    # observation_only / used_for_* all have safe defaults.
    assert {"provider", "symbol", "timeframe"} <= required


def test_parse_valid_payload_keeps_safety_flags_locked():
    spec = parse_decision_screen_spec(
        provider="openai",
        payload=_good_payload(),
        symbol="EURUSD=X",
        timeframe="M5",
    )
    assert isinstance(spec, AiDecisionScreenSpec)
    assert spec.observation_only is True
    assert spec.used_for_ready is False
    assert spec.used_for_notification is False
    assert spec.used_for_trading is False
    assert spec.final_status == "WAIT_BREAKOUT"
    assert spec.lines and spec.lines[0].kind == "neckline"


def test_parse_force_resets_safety_flags_when_silent():
    payload = _good_payload()
    # Model omits the safety flags.
    spec = parse_decision_screen_spec(
        provider="openai",
        payload=payload,
        symbol="EURUSD=X",
        timeframe="M5",
    )
    assert spec.observation_only is True
    assert spec.used_for_ready is False
    assert spec.used_for_notification is False
    assert spec.used_for_trading is False


def test_parse_downgrades_when_used_for_ready_true():
    payload = _good_payload()
    payload["used_for_ready"] = True
    spec = parse_decision_screen_spec(
        provider="openai",
        payload=payload,
        symbol="EURUSD=X",
        timeframe="M5",
    )
    assert spec.final_status == "UNKNOWN"
    assert any("used_for_ready" in p for p in spec.problems)
    # Even after downgrade, the safety flags themselves remain safe.
    assert spec.used_for_ready is False
    assert spec.used_for_notification is False
    assert spec.used_for_trading is False
    assert spec.observation_only is True


def test_parse_downgrades_when_observation_only_false():
    payload = _good_payload()
    payload["observation_only"] = False
    spec = parse_decision_screen_spec(
        provider="claude",
        payload=payload,
        symbol="EURUSD=X",
        timeframe="M5",
    )
    assert spec.final_status == "UNKNOWN"
    assert any("observation_only" in p for p in spec.problems)


def test_parse_downgrades_when_used_for_trading_true():
    payload = _good_payload()
    payload["used_for_trading"] = True
    spec = parse_decision_screen_spec(
        provider="openai",
        payload=payload,
        symbol="EURUSD=X",
        timeframe="M5",
    )
    assert spec.final_status == "UNKNOWN"
    assert any("used_for_trading" in p for p in spec.problems)


def test_parse_bad_json_returns_unknown():
    spec = parse_decision_screen_spec(
        provider="openai",
        payload="not json",
        symbol="EURUSD=X",
        timeframe="M5",
    )
    assert spec.final_status == "UNKNOWN"
    assert any("invalid JSON" in p for p in spec.problems)


def test_parse_schema_violation_returns_unknown():
    payload = _good_payload()
    payload["side"] = "WHATEVER"  # outside enum
    spec = parse_decision_screen_spec(
        provider="claude",
        payload=payload,
        symbol="EURUSD=X",
        timeframe="M5",
    )
    assert spec.final_status == "UNKNOWN"


def test_safe_unknown_spec_helper_keeps_safety_locked():
    spec = safe_unknown_spec(
        provider="openai",
        symbol="EURUSD=X",
        timeframe="M5",
        reason="openai_disabled",
    )
    assert spec.observation_only is True
    assert spec.used_for_ready is False
    assert spec.used_for_notification is False
    assert spec.used_for_trading is False
    assert spec.final_status == "UNKNOWN"
    assert spec.problems == ["openai_disabled"]
