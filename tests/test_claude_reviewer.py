from __future__ import annotations

import sys
from types import SimpleNamespace

from fx_monitor.adapters import build_monitor_case_from_royal_road_payload
from fx_monitor.ai.claude_reviewer import ClaudeReviewer


def test_claude_reviewer_disabled_returns_unknown(monkeypatch, ready_payload):
    monkeypatch.setenv("ANTHROPIC_ENABLED", "false")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    case = build_monitor_case_from_royal_road_payload(ready_payload)
    review = ClaudeReviewer().review(case)

    assert review.provider == "claude"
    assert review.verdict == "UNKNOWN"
    assert review.bias == "none"
    assert any("anthropic_disabled" in x for x in review.missing + review.reasons)


def test_claude_reviewer_missing_key_returns_unknown(monkeypatch, ready_payload):
    monkeypatch.setenv("ANTHROPIC_ENABLED", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    case = build_monitor_case_from_royal_road_payload(ready_payload)
    review = ClaudeReviewer().review(case)

    assert review.verdict == "UNKNOWN"
    assert any("anthropic_api_key_missing" in x for x in review.missing + review.reasons)


def _install_fake_anthropic(monkeypatch, message_obj):
    class _FakeMessages:
        def create(self, **_):
            return message_obj

    class _FakeAnthropic:
        def __init__(self, **_):
            self.messages = _FakeMessages()

    fake_module = SimpleNamespace(Anthropic=_FakeAnthropic)
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)


def test_claude_reviewer_tool_use_missing_returns_unknown(monkeypatch, ready_payload):
    monkeypatch.setenv("ANTHROPIC_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-fake-key")

    text_only = SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")])
    _install_fake_anthropic(monkeypatch, text_only)

    case = build_monitor_case_from_royal_road_payload(ready_payload)
    review = ClaudeReviewer().review(case)

    assert review.verdict == "UNKNOWN"
    assert any("anthropic_tool_use_missing" in x for x in review.missing + review.reasons)


def test_claude_reviewer_api_failure_returns_unknown(monkeypatch, ready_payload):
    monkeypatch.setenv("ANTHROPIC_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-fake-key")

    class _FakeMessages:
        def create(self, **_):
            raise RuntimeError("simulated network failure")

    class _FakeAnthropic:
        def __init__(self, **_):
            self.messages = _FakeMessages()

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeAnthropic))

    case = build_monitor_case_from_royal_road_payload(ready_payload)
    review = ClaudeReviewer().review(case)

    assert review.verdict == "UNKNOWN"
    assert any("anthropic_review_failed" in x for x in review.missing + review.reasons)


def test_claude_reviewer_schema_violation_returns_unknown(monkeypatch, ready_payload):
    monkeypatch.setenv("ANTHROPIC_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-fake-key")

    bad_block = SimpleNamespace(
        type="tool_use",
        name="submit_ai_royal_road_review",
        input={"verdict": "PASS", "bias": "sideways", "confidence": 0.5, "reasons": []},
    )
    msg = SimpleNamespace(content=[bad_block])
    _install_fake_anthropic(monkeypatch, msg)

    case = build_monitor_case_from_royal_road_payload(ready_payload)
    review = ClaudeReviewer().review(case)

    assert review.verdict == "UNKNOWN"
