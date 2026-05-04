from __future__ import annotations

from fx_monitor.ai.decision_screen_prompt_builder import build_decision_screen_prompt


def test_decision_screen_prompt_pins_japanese_royal_road_instructions():
    prompt = build_decision_screen_prompt(
        market_analysis_pack={"symbol": "EURUSD=X", "timeframe": "M5"},
        provider="openai",
    )
    text = prompt.system + "\n" + prompt.user

    for token in [
        "王道手順",
        "売買指示ではありません",
        "READY通知ではありません",
        "観測専用",
        "盲信しないでください",
        "根拠が弱い線を採用しない",
        "reason_ja",
        "used_for_ready は必ず false",
        "used_for_trading は必ず false",
        "used_for_notification は必ず false",
        "observation_only は必ず true",
        "AiDecisionScreenSpec",
    ]:
        assert token in text, f"prompt missing required guidance {token!r}"


def test_decision_screen_prompt_embeds_pack_and_provider():
    pack = {"symbol": "USDJPY=X", "timeframe": "H1", "instructions_for_ai": ["foo"]}
    prompt = build_decision_screen_prompt(
        market_analysis_pack=pack, provider="claude"
    )
    assert '"USDJPY=X"' in prompt.user
    assert '"H1"' in prompt.user
    assert 'provider = "claude"' in prompt.user
