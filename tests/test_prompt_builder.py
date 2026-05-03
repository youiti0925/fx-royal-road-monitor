from __future__ import annotations

from fx_monitor.ai.prompt_builder import build_prompt
from fx_monitor.knowledge.loader import load_knowledge_pack


def test_prompt_includes_pack_schema_and_payload(passing_payload):
    pack = load_knowledge_pack()
    prompt = build_prompt(passing_payload, pack)

    assert "royal-road" in prompt.system.lower() or "royal road" in prompt.system.lower()
    assert "json" in prompt.system.lower()

    assert pack.text in prompt.user, "knowledge pack must be embedded verbatim"
    assert "ReviewResult" in prompt.user, "schema title should be present"
    assert "USDJPY" in prompt.user
    assert "HH-HL" in prompt.user
    assert "breakout" in prompt.user


def test_prompt_includes_detailed_royal_road_terms(passing_payload):
    pack = load_knowledge_pack()
    prompt = build_prompt(passing_payload, pack)
    text = prompt.user
    for token in [
        "WNL",
        "WSL",
        "WTP",
        "SNL",
        "SIL",
        "STP",
        "STL",
        "confirmation_candle is P0",
        "RR >= 2.0",
        "WAIT_BREAKOUT",
        "WAIT_RETEST",
        "WAIT_TRIGGER",
        "WAIT_EVENT_CLEAR",
        "Numeric trendline",
        "Structural trendline",
    ]:
        assert token in text, f"prompt must contain {token!r}"


def test_prompt_includes_required_step_keys(passing_payload):
    pack = load_knowledge_pack()
    prompt = build_prompt(passing_payload, pack)
    for key in (
        "wave_pattern",
        "neckline",
        "breakout",
        "retest",
        "confirmation_candle",
        "entry",
        "stop",
        "target",
        "rr",
        "event",
    ):
        assert key in prompt.user, f"schema enum should expose step key {key!r}"


def test_prompt_system_warns_against_general_knowledge(passing_payload):
    pack = load_knowledge_pack()
    prompt = build_prompt(passing_payload, pack)
    sys = prompt.system.lower()
    assert "general market knowledge" in sys
    assert "unknown" in sys
