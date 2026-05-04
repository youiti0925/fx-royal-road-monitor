from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(".github/workflows/publish_mvp1_preview.yml")


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_publish_preview_workflow_exists():
    assert WORKFLOW.exists(), f"missing workflow: {WORKFLOW}"


def test_publish_preview_workflow_is_manual_only():
    text = _text()
    assert "workflow_dispatch" in text
    assert "schedule:" not in text


def test_publish_preview_workflow_uses_ai_authored_mode():
    text = _text()
    assert "--mode ai-authored" in text


def test_publish_preview_workflow_uses_secrets():
    text = _text()
    assert "${{ secrets.OPENAI_API_KEY }}" in text
    assert "${{ secrets.ANTHROPIC_API_KEY }}" in text
    assert 'OPENAI_ENABLED: "true"' in text
    assert 'ANTHROPIC_ENABLED: "true"' in text


def test_publish_preview_workflow_commits_refreshed_directory():
    text = _text()
    assert "git add docs/mvp1_current_preview" in text
    assert (
        'docs: refresh AI-authored MVP1 preview' in text
        or 'docs: refresh AI-authored MVP1 preview"' in text
    )


def test_publish_preview_workflow_does_not_enable_trading_or_paper():
    text = _text().lower()
    forbidden = [
        "oanda",
        "paper_broker",
        "paper_trade",
        "live_order",
        "place_order",
    ]
    for token in forbidden:
        assert token not in text, f"workflow must not contain {token!r}"
