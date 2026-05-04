from __future__ import annotations

from pathlib import Path

from fx_monitor.logging.review_log import read_review_log
from fx_monitor.logging.review_report import (
    build_review_report_markdown,
    summarize_review_records,
    write_review_report,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_read_review_log_sample():
    records = read_review_log(FIXTURES / "review_log_sample.jsonl")
    assert len(records) == 2
    assert records[0]["mode"] == "draft_ai_review"


def test_read_review_log_missing_file_returns_empty(tmp_path):
    records = read_review_log(tmp_path / "missing.jsonl")
    assert records == []


def test_read_review_log_bad_line_does_not_crash(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"ok": true}\nnot-json\n', encoding="utf-8")

    records = read_review_log(path)
    assert len(records) == 2
    assert records[1]["mode"] == "invalid_json"


def test_summarize_review_records_counts_missing_and_disagreements():
    records = read_review_log(FIXTURES / "review_log_sample.jsonl")
    summary = summarize_review_records(records)

    assert summary["total_records"] == 2
    assert summary["decisions"]["SUPPRESSED"] == 2
    assert summary["openai_verdicts"]["UNKNOWN"] == 1
    assert summary["openai_verdicts"]["WARN"] == 1
    assert summary["compare_results"]["INSUFFICIENT"] == 1
    assert summary["compare_results"]["DISAGREE"] == 1

    openai_missing_values = {x["value"] for x in summary["top_openai_missing"]}
    assert "confirmation_candle" in openai_missing_values
    assert "retest" in openai_missing_values

    claude_disagreements = {x["value"] for x in summary["top_claude_disagreements"]}
    assert "line_unclear" in claude_disagreements


def test_summarize_pivots_and_zones_stats():
    records = read_review_log(FIXTURES / "review_log_sample.jsonl")
    summary = summarize_review_records(records)
    assert summary["pivots"]["count"] == 2
    assert summary["pivots"]["min"] == 4
    assert summary["pivots"]["max"] == 6
    assert summary["zones"]["count"] == 2


def test_summary_safety_flags():
    summary = summarize_review_records([])
    assert summary["safety"]["used_for_notification"] is False
    assert summary["safety"]["used_for_ready"] is False
    assert summary["safety"]["offline_analysis_only"] is True


def test_build_review_report_markdown_contains_safety_and_top_missing():
    records = read_review_log(FIXTURES / "review_log_sample.jsonl")
    summary = summarize_review_records(records)
    md = build_review_report_markdown(summary)

    assert "Offline analysis only" in md
    assert "Not used for READY" in md
    assert "Not used for notification" in md
    assert "confirmation_candle" in md
    assert "line_unclear" in md


def test_write_review_report_outputs_md_and_json(tmp_path):
    md_path = tmp_path / "report.md"
    json_path = tmp_path / "summary.json"

    summary = write_review_report(
        log_path=FIXTURES / "review_log_sample.jsonl",
        markdown_path=md_path,
        json_path=json_path,
    )

    assert summary["total_records"] == 2
    assert md_path.exists()
    assert json_path.exists()
    md_text = md_path.read_text(encoding="utf-8")
    assert "FX Monitor Draft AI Review Report" in md_text
    assert "Offline analysis only" in md_text


def test_write_review_report_creates_parent_dirs(tmp_path):
    md_path = tmp_path / "deep" / "nested" / "report.md"
    json_path = tmp_path / "deep" / "nested" / "summary.json"
    write_review_report(
        log_path=FIXTURES / "review_log_sample.jsonl",
        markdown_path=md_path,
        json_path=json_path,
    )
    assert md_path.exists()
    assert json_path.exists()


def test_cli_runs_via_subprocess(tmp_path):
    import subprocess
    import sys

    md_path = tmp_path / "report.md"
    json_path = tmp_path / "summary.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fx_monitor.app.review_report",
            "--log",
            str(FIXTURES / "review_log_sample.jsonl"),
            "--md",
            str(md_path),
            "--json",
            str(json_path),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "Review records: 2" in result.stdout
    assert "Markdown report:" in result.stdout
    assert "JSON summary:" in result.stdout
    assert md_path.exists()
    assert json_path.exists()
