from __future__ import annotations

from pathlib import Path

REPORT = Path("docs/MVP1_OBSERVATION_PIPELINE_FREEZE_REPORT.md")
README = Path("README.md")


def test_mvp1_freeze_report_exists():
    assert REPORT.exists(), f"missing freeze report: {REPORT}"


def test_mvp1_freeze_report_pins_safety_contract():
    text = REPORT.read_text(encoding="utf-8")

    for token in [
        "observation-only",
        "does not produce READY",
        "does not dispatch notifications",
        "does not trade",
        "entry_plan.entry_status = HOLD",
        "p0_pass = false",
        "ready_eligible = false",
        "decision = SUPPRESSED",
        "dispatch = not called",
        "READY = impossible from feed mode",
    ]:
        assert token in text, f"freeze report missing required token {token!r}"


def test_mvp1_freeze_report_pins_artifact_review_order():
    text = REPORT.read_text(encoding="utf-8")

    for token in [
        "out/dashboard.html",
        "out/draft_chart.png",
        "out/diagnostics.json",
        "out/review_report.md",
        "out/rich_draft_compare.json",
    ]:
        assert token in text, f"freeze report missing artifact reference {token!r}"


def test_mvp1_freeze_report_lists_unapproved_phases():
    text = REPORT.read_text(encoding="utf-8")
    assert "P4" in text and "not approved yet" in text
    assert "P5" in text
    assert "P6" in text
    assert "Trading" in text and "out of scope" in text


def test_readme_links_to_mvp1_freeze_report():
    assert (
        "docs/MVP1_OBSERVATION_PIPELINE_FREEZE_REPORT.md"
        in README.read_text(encoding="utf-8")
    )
