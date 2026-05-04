from __future__ import annotations

import json
from pathlib import Path

PREVIEW = Path("docs/mvp1_current_preview")
README = Path("README.md")


def test_mvp1_preview_files_exist():
    for name in (
        "index.html",
        "dashboard.html",
        "draft_chart.png",
        "diagnostics.json",
        "review_report.md",
        "review_report.json",
        "review_log.jsonl",
    ):
        p = PREVIEW / name
        assert p.exists(), f"missing preview file: {p}"


def test_mvp1_preview_index_contains_safety_text():
    html_text = (PREVIEW / "index.html").read_text(encoding="utf-8")
    assert "MVP-1 Observation Pipeline Preview" in html_text
    assert "SAFE: offline analysis only" in html_text or "CHECK SAFETY FLAGS" in html_text
    assert "SUPPRESSED" in html_text
    assert "NOT READY ELIGIBLE" in html_text
    assert "draft_chart.png" in html_text
    assert "dashboard.html" in html_text
    assert "diagnostics.json" in html_text
    assert "review_report.md" in html_text


def test_mvp1_preview_index_uses_relative_urls():
    html_text = (PREVIEW / "index.html").read_text(encoding="utf-8")
    # All embedded resources must use relative URLs so htmlpreview.github.io
    # can resolve them inside docs/mvp1_current_preview/.
    assert "src=\"./draft_chart.png\"" in html_text
    assert "href=\"./dashboard.html\"" in html_text


def test_mvp1_preview_does_not_claim_ready():
    html_text = (PREVIEW / "index.html").read_text(encoding="utf-8")
    forbidden = [
        "READY notification enabled",
        "dispatch_called = true",
        "ready_allowed = true",
        "used_for_ready = true",
        "used_for_notification = true",
        "<td>True</td><th>safety.ready_allowed</th>",
    ]
    for token in forbidden:
        assert token not in html_text, f"preview index must not contain {token!r}"


def test_mvp1_preview_diagnostics_safety_flags():
    data = json.loads((PREVIEW / "diagnostics.json").read_text(encoding="utf-8"))
    assert data["decision"]["level"] == "SUPPRESSED"
    assert data["safety"]["ready_allowed"] is False
    assert data["safety"]["dispatch_called"] is False
    assert data["draft"]["observation_only"] is True
    assert data["draft"]["used_in_final_action"] is False
    assert data["draft"]["entry_status"] == "HOLD"
    assert data["draft"]["p0_pass"] is False
    assert data["draft"]["rich_draft"]["ready_eligible"] is False
    assert data["draft"]["rich_draft"]["p0_pass"] is False


def test_mvp1_preview_review_report_safety_flags():
    data = json.loads((PREVIEW / "review_report.json").read_text(encoding="utf-8"))
    assert data["safety"]["used_for_ready"] is False
    assert data["safety"]["used_for_notification"] is False
    assert data["safety"]["offline_analysis_only"] is True


def test_mvp1_preview_chart_is_real_png_with_pattern():
    """The preview must show actual draft lines, not the empty placeholder.

    A populated chart (with P1/NL/P2/BR + lines) is at least ~30 KB; the
    matplotlib empty-placeholder card is much smaller. We use a generous
    floor so this remains stable across matplotlib font cache states.
    """
    chart = PREVIEW / "draft_chart.png"
    assert chart.stat().st_size > 30000, (
        f"preview chart looks like a placeholder ({chart.stat().st_size} B) — "
        "rebuild the preview with python -m fx_monitor.app.build_preview"
    )
    # diagnostics should agree the rich draft is populated.
    data = json.loads((PREVIEW / "diagnostics.json").read_text(encoding="utf-8"))
    rich = data["draft"]["rich_draft"]
    assert rich["pattern_kind"] in (
        "possible_double_top",
        "possible_double_bottom",
    )
    assert rich["wave_lines"] >= 3
    assert rich["structural_lines"] >= 4


def test_readme_links_to_mvp1_preview():
    text = README.read_text(encoding="utf-8")
    assert "docs/mvp1_current_preview/index.html" in text
    assert "htmlpreview.github.io" in text
