"""Static (file-content) checks for the monitor workflow.

These tests do not invoke GitHub Actions; they just pin a few invariants
in ``.github/workflows/monitor.yml`` so a future edit cannot silently
remove the safety guards or the artifact upload.
"""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(".github/workflows/monitor.yml")


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_file_exists():
    assert WORKFLOW.exists(), f"missing workflow: {WORKFLOW}"


def test_monitor_workflow_is_dry_run_and_uploads_artifacts():
    text = _text()

    # Hard safety defaults must be present.
    assert 'DRY_RUN: "true"' in text
    assert 'FX_MONITOR_REVIEW_DRAFT_WITH_AI: "true"' in text
    assert 'FX_MONITOR_REVIEW_LOG_PATH: "out/review_log.jsonl"' in text

    # Notification card attachment is disabled for the schedule.
    assert 'FX_MONITOR_RENDER_CARD: "false"' in text
    assert 'FX_MONITOR_ATTACH_CARD: "false"' in text

    # Artifact paths and uploader.
    assert "out/review_log.jsonl" in text
    assert "out/review_report.md" in text
    assert "out/review_report.json" in text
    assert "actions/upload-artifact" in text


def test_monitor_workflow_runs_draft_review_only_on_schedule_or_dispatch():
    text = _text()
    assert "schedule" in text
    assert "workflow_dispatch" in text
    # The draft-review job must guard itself.
    assert (
        "if: github.event_name == 'schedule' || "
        "github.event_name == 'workflow_dispatch'"
    ) in text


def test_monitor_workflow_does_not_enable_live_or_trading():
    text = _text().lower()
    forbidden = [
        "oanda",
        "paper_broker",
        "paper_trade",
        "live_order",
        "place_order",
        "auto_trade=true",
        "auto_trade: \"true\"",
        "auto_trade: 'true'",
    ]
    for token in forbidden:
        assert token not in text, f"workflow must not contain {token!r}"


def test_monitor_workflow_runs_draft_review_command():
    text = _text()
    assert "python -m fx_monitor.app.run_once" in text
    assert "python -m fx_monitor.app.review_report" in text


def test_monitor_workflow_uploads_diagnostics_artifact():
    text = _text()
    assert 'FX_MONITOR_DIAGNOSTICS_PATH: "out/diagnostics.json"' in text
    assert "out/diagnostics.json" in text
