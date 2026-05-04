from __future__ import annotations

from pathlib import Path

RUNBOOK = Path("docs/RUNBOOK_SCHEDULED_DRAFT_REVIEW.md")
README = Path("README.md")


def test_scheduled_draft_review_runbook_exists():
    assert RUNBOOK.exists(), f"missing runbook: {RUNBOOK}"


def test_runbook_pins_safety_contract():
    text = RUNBOOK.read_text(encoding="utf-8")

    for token in [
        "observation-only",
        "not used for READY",
        "not used for notification",
        "dashboard.html",
        "diagnostics.json",
        "review_report.json",
        "Decision: SUPPRESSED",
        "No [READY]",
        "CHECK SAFETY FLAGS",
        "DRY_RUN = true",
    ]:
        assert token in text, f"runbook missing required token {token!r}"


def test_runbook_warns_not_to_enable_notifications_too_early():
    text = RUNBOOK.read_text(encoding="utf-8")

    assert "Do not proceed to real notifications" in text
    assert "draft-to-rich-payload promotion plan" in text


def test_runbook_says_open_dashboard_first():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "first file to check" in text or "first file to open" in text


def test_readme_links_to_runbook():
    text = README.read_text(encoding="utf-8")
    assert "docs/RUNBOOK_SCHEDULED_DRAFT_REVIEW.md" in text
