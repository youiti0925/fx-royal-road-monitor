"""Verify the visual_review path actually delivers image bytes to the API.

We monkey-patch the OpenAI / Anthropic SDKs with fakes that capture the
request kwargs, then assert that the captured payload includes the image
content (data URL for OpenAI, base64 source for Claude).
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

from fx_monitor.ai.claude_reviewer import ClaudeReviewer
from fx_monitor.ai.openai_reviewer import OpenAIReviewer

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image-content"


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
def _install_fake_openai(monkeypatch, response_text: str, captured: dict):
    class _FakeResp:
        output_text = response_text

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeResp()

    class _FakeClient:
        def __init__(self, **_):
            self.responses = _FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeClient))


def test_openai_visual_review_receives_image_bytes(monkeypatch):
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-fake-key")

    captured: dict = {}
    response = json.dumps(
        {
            "schema_version": "visual_review_v1",
            "verdict": "PASS",
            "readability": "GOOD",
            "language": "JA",
            "royal_road_clarity": "GOOD",
            "line_visibility": "GOOD",
            "safety_clarity": "GOOD",
            "problems": [],
            "required_fixes": [],
            "summary_ja": "OK",
        }
    )
    _install_fake_openai(monkeypatch, response, captured)

    review = OpenAIReviewer().visual_review(
        image_bytes=PNG_BYTES, context_summary="ctx"
    )
    assert review.verdict == "PASS"
    assert review.language == "JA"

    assert "input" in captured
    flat = json.dumps(captured["input"])
    assert "input_image" in flat
    assert "data:image/png;base64," in flat


def test_openai_visual_review_unknown_when_disabled(monkeypatch):
    monkeypatch.setenv("OPENAI_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    review = OpenAIReviewer().visual_review(image_bytes=PNG_BYTES)
    assert review.verdict == "UNKNOWN"
    assert any("openai_disabled" in p for p in review.problems)


def test_openai_visual_review_unknown_when_no_key(monkeypatch):
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    review = OpenAIReviewer().visual_review(image_bytes=PNG_BYTES)
    assert review.verdict == "UNKNOWN"
    assert any("openai_api_key_missing" in p for p in review.problems)


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------
def _install_fake_anthropic(monkeypatch, message_obj, captured: dict):
    class _FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return message_obj

    class _FakeAnthropic:
        def __init__(self, **_):
            self.messages = _FakeMessages()

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=_FakeAnthropic))


def test_claude_visual_review_receives_image_bytes(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-fake-key")

    captured: dict = {}
    tool_block = SimpleNamespace(
        type="tool_use",
        name="submit_visual_review",
        input={
            "schema_version": "visual_review_v1",
            "verdict": "PASS",
            "readability": "GOOD",
            "language": "JA",
            "royal_road_clarity": "GOOD",
            "line_visibility": "GOOD",
            "safety_clarity": "GOOD",
            "problems": [],
            "required_fixes": [],
            "summary_ja": "OK",
        },
    )
    msg = SimpleNamespace(content=[tool_block])
    _install_fake_anthropic(monkeypatch, msg, captured)

    review = ClaudeReviewer().visual_review(
        image_bytes=PNG_BYTES, context_summary="ctx"
    )
    assert review.verdict == "PASS"
    assert review.language == "JA"

    assert "messages" in captured
    flat = json.dumps(captured["messages"])
    assert '"image"' in flat
    assert '"base64"' in flat
    assert '"image/png"' in flat


def test_claude_visual_review_unknown_when_disabled(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_ENABLED", "false")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    review = ClaudeReviewer().visual_review(image_bytes=PNG_BYTES)
    assert review.verdict == "UNKNOWN"
    assert any("anthropic_disabled" in p for p in review.problems)


def test_claude_visual_review_unknown_when_no_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_ENABLED", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    review = ClaudeReviewer().visual_review(image_bytes=PNG_BYTES)
    assert review.verdict == "UNKNOWN"
    assert any("anthropic_api_key_missing" in p for p in review.problems)


def test_claude_visual_review_tool_use_missing_returns_unknown(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-fake-key")

    captured: dict = {}
    text_only = SimpleNamespace(content=[SimpleNamespace(type="text", text="hi")])
    _install_fake_anthropic(monkeypatch, text_only, captured)

    review = ClaudeReviewer().visual_review(image_bytes=PNG_BYTES)
    assert review.verdict == "UNKNOWN"
    assert any("anthropic_visual_tool_use_missing" in p for p in review.problems)
