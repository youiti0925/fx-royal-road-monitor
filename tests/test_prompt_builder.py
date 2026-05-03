from __future__ import annotations

from fx_monitor.ai.prompt_builder import build_prompt
from fx_monitor.knowledge.loader import load_knowledge_pack


def test_prompt_includes_pack_schema_and_payload(passing_payload):
    pack = load_knowledge_pack()
    prompt = build_prompt(passing_payload, pack)

    # System instruction must mention the contract.
    assert "knowledge pack" in prompt.system.lower()
    assert "json" in prompt.system.lower()

    # User prompt must embed the full pack verbatim, the schema, and the payload.
    assert pack.text in prompt.user, "knowledge pack must be embedded verbatim"
    assert "ReviewResult" in prompt.user, "schema title should be present"
    assert "USDJPY" in prompt.user
    assert "HH-HL" in prompt.user
    assert "breakout" in prompt.user
