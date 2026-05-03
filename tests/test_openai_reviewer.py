from __future__ import annotations

from fx_monitor.adapters import build_monitor_case_from_royal_road_payload
from fx_monitor.ai.openai_reviewer import OpenAIReviewer


def test_openai_reviewer_disabled_returns_unknown(monkeypatch, ready_payload):
    monkeypatch.setenv("OPENAI_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    case = build_monitor_case_from_royal_road_payload(ready_payload)
    review = OpenAIReviewer().review(case)

    assert review.provider == "openai"
    assert review.verdict == "UNKNOWN"
    assert review.bias == "none"
    assert any("openai_disabled" in x for x in review.missing + review.reasons)


def test_openai_reviewer_missing_key_returns_unknown(monkeypatch, ready_payload):
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    case = build_monitor_case_from_royal_road_payload(ready_payload)
    review = OpenAIReviewer().review(case)

    assert review.verdict == "UNKNOWN"
    assert any("openai_api_key_missing" in x for x in review.missing + review.reasons)


def test_openai_reviewer_api_failure_returns_unknown(monkeypatch, ready_payload):
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-fake-key")

    import fx_monitor.ai.openai_reviewer as mod

    class _FakeResponses:
        def create(self, **_):
            raise RuntimeError("simulated network failure")

    class _FakeClient:
        def __init__(self, **_):
            self.responses = _FakeResponses()

    fake_openai_module = type("F", (), {"OpenAI": _FakeClient})
    monkeypatch.setitem(__import__("sys").modules, "openai", fake_openai_module)

    case = build_monitor_case_from_royal_road_payload(ready_payload)
    review = mod.OpenAIReviewer().review(case)

    assert review.verdict == "UNKNOWN"
    assert any("openai_review_failed" in x for x in review.missing + review.reasons)


def test_openai_reviewer_schema_violation_returns_unknown(monkeypatch, ready_payload):
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-fake-key")

    import fx_monitor.ai.openai_reviewer as mod

    class _FakeResponse:
        # bias=sideways is not in our enum; parse_review must downgrade.
        output_text = '{"verdict":"PASS","bias":"sideways","confidence":0.5,"reasons":[]}'

    class _FakeResponses:
        def create(self, **_):
            return _FakeResponse()

    class _FakeClient:
        def __init__(self, **_):
            self.responses = _FakeResponses()

    monkeypatch.setitem(
        __import__("sys").modules, "openai", type("F", (), {"OpenAI": _FakeClient})
    )

    case = build_monitor_case_from_royal_road_payload(ready_payload)
    review = mod.OpenAIReviewer().review(case)

    assert review.verdict == "UNKNOWN"
