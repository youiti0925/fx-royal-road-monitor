from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fx_monitor.logging.dashboard import build_dashboard_html, write_dashboard

FIXTURES = Path(__file__).parent / "fixtures"


def _safe_summary() -> dict:
    return {
        "total_records": 1,
        "decisions": {"SUPPRESSED": 1},
        "compare_results": {"INSUFFICIENT": 1},
        "top_openai_missing": [{"value": "confirmation_candle", "count": 1}],
        "top_claude_missing": [{"value": "trendline", "count": 1}],
        "top_openai_disagreements": [],
        "top_claude_disagreements": [],
        "safety": {
            "used_for_ready": False,
            "used_for_notification": False,
            "offline_analysis_only": True,
        },
    }


def _safe_diagnostics() -> dict:
    return {
        "feed": {"symbol": "EURUSD=X", "candles": 5},
        "draft": {"pivots": 4, "observation_only": True},
        "rule": {"verdict": "UNKNOWN"},
        "ai": {
            "openai": {"verdict": "UNKNOWN", "missing": ["confirmation_candle"]},
            "claude": {"verdict": "UNKNOWN", "missing": ["trendline"]},
            "compare": {"result": "INSUFFICIENT"},
        },
        "decision": {"level": "SUPPRESSED"},
        "safety": {"ready_allowed": False, "dispatch_called": False},
    }


def test_build_dashboard_html_contains_safety_and_core_values():
    html_text = build_dashboard_html(
        diagnostics=_safe_diagnostics(),
        review_summary=_safe_summary(),
    )

    assert "SAFE: offline analysis only" in html_text
    assert "EURUSD=X" in html_text
    assert "SUPPRESSED" in html_text
    assert "confirmation_candle" in html_text
    assert "trendline" in html_text
    assert "not used for READY" in html_text
    assert "not used for notification" in html_text


def test_build_dashboard_html_flips_to_check_when_safety_violated():
    diag = _safe_diagnostics()
    diag["safety"]["ready_allowed"] = True
    html_text = build_dashboard_html(
        diagnostics=diag,
        review_summary=_safe_summary(),
    )
    assert "CHECK SAFETY FLAGS" in html_text
    assert "SAFE: offline analysis only" not in html_text


def test_build_dashboard_html_escapes_user_values():
    diag = _safe_diagnostics()
    diag["feed"]["symbol"] = "<script>alert(1)</script>"
    html_text = build_dashboard_html(
        diagnostics=diag,
        review_summary=_safe_summary(),
    )
    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_text


def test_write_dashboard_outputs_html(tmp_path):
    out = tmp_path / "dashboard.html"
    path = write_dashboard(
        diagnostics_path=FIXTURES / "diagnostics_sample.json",
        review_summary_path=FIXTURES / "review_report_sample.json",
        html_path=out,
    )

    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "FX Monitor Draft Review Dashboard" in text
    assert "EURUSD=X" in text
    assert "possible_double_top" in text
    assert "confirmation_candle" in text
    assert "line_unclear" in text


def test_write_dashboard_handles_missing_input_files(tmp_path):
    out = tmp_path / "dashboard.html"
    path = write_dashboard(
        diagnostics_path=tmp_path / "nope1.json",
        review_summary_path=tmp_path / "nope2.json",
        html_path=out,
    )
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    # With both inputs missing the safety check defaults to "bad" because
    # used_for_ready/used_for_notification are not False.
    assert "FX Monitor Draft Review Dashboard" in text


def test_dashboard_cli_runs_via_subprocess(tmp_path):
    out = tmp_path / "dashboard.html"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fx_monitor.app.dashboard",
            "--diagnostics",
            str(FIXTURES / "diagnostics_sample.json"),
            "--summary",
            str(FIXTURES / "review_report_sample.json"),
            "--html",
            str(out),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "Dashboard:" in result.stdout
    assert out.exists()


def test_dashboard_safety_flips_if_rich_draft_ready_eligible():
    diagnostics = {
        "draft": {
            "rich_draft": {
                "ready_eligible": True,
                "p0_pass": False,
            }
        },
        "decision": {"level": "SUPPRESSED"},
        "safety": {"ready_allowed": False, "dispatch_called": False},
    }
    summary = {
        "safety": {
            "used_for_ready": False,
            "used_for_notification": False,
            "offline_analysis_only": True,
        }
    }

    html_text = build_dashboard_html(
        diagnostics=diagnostics, review_summary=summary
    )
    assert "CHECK SAFETY FLAGS" in html_text


def test_dashboard_safety_flips_if_rich_draft_p0_pass_true():
    diagnostics = {
        "draft": {
            "rich_draft": {
                "ready_eligible": False,
                "p0_pass": True,
            }
        },
        "decision": {"level": "SUPPRESSED"},
        "safety": {"ready_allowed": False, "dispatch_called": False},
    }
    summary = {
        "safety": {
            "used_for_ready": False,
            "used_for_notification": False,
            "offline_analysis_only": True,
        }
    }
    html_text = build_dashboard_html(
        diagnostics=diagnostics, review_summary=summary
    )
    assert "CHECK SAFETY FLAGS" in html_text


def test_dashboard_renders_rich_draft_card():
    diagnostics = {
        "draft": {
            "rich_draft": {
                "schema_version": "rich_royal_road_draft_v1",
                "ready_eligible": False,
                "pattern_kind": "possible_double_top",
                "wave_lines": 3,
                "structural_lines": 4,
                "p0_pass": False,
            }
        },
        "decision": {"level": "SUPPRESSED"},
        "safety": {"ready_allowed": False, "dispatch_called": False},
    }
    summary = {
        "safety": {
            "used_for_ready": False,
            "used_for_notification": False,
            "offline_analysis_only": True,
        }
    }
    html_text = build_dashboard_html(
        diagnostics=diagnostics, review_summary=summary
    )
    assert "Rich draft" in html_text
    assert "rich_royal_road_draft_v1" in html_text
    assert "possible_double_top" in html_text


def test_dashboard_shows_open_draft_chart_link_when_chart_path_set():
    diagnostics = {
        "draft": {
            "rich_draft": {
                "ready_eligible": False,
                "p0_pass": False,
                "chart_path": "out/draft_chart.png",
                "chart_rendered": True,
            }
        },
        "decision": {"level": "SUPPRESSED"},
        "safety": {"ready_allowed": False, "dispatch_called": False},
    }
    summary = {
        "safety": {
            "used_for_ready": False,
            "used_for_notification": False,
            "offline_analysis_only": True,
        }
    }

    html_text = build_dashboard_html(
        diagnostics=diagnostics, review_summary=summary
    )
    assert "Open draft chart" in html_text
    # Use relative filename only (works inside artifact zip).
    assert "href='draft_chart.png'" in html_text
    assert "SAFE: offline analysis only" in html_text


def test_dashboard_safety_still_flips_red_with_chart_when_ready_eligible():
    diagnostics = {
        "draft": {
            "rich_draft": {
                "ready_eligible": True,
                "p0_pass": False,
                "chart_path": "out/draft_chart.png",
                "chart_rendered": True,
            }
        },
        "decision": {"level": "SUPPRESSED"},
        "safety": {"ready_allowed": False, "dispatch_called": False},
    }
    summary = {
        "safety": {
            "used_for_ready": False,
            "used_for_notification": False,
            "offline_analysis_only": True,
        }
    }
    html_text = build_dashboard_html(
        diagnostics=diagnostics, review_summary=summary
    )
    assert "CHECK SAFETY FLAGS" in html_text
