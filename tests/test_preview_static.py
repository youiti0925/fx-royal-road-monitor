from __future__ import annotations

import json
from pathlib import Path

PREVIEW = Path("docs/mvp1_current_preview")
README = Path("README.md")


def test_mvp1_preview_files_exist():
    for name in (
        "index.html",
        "decision_screen.html",
        "decision_screen.png",
        "dashboard.html",
        "draft_chart.png",
        "diagnostics.json",
        "review_report.md",
        "review_report.json",
        "review_log.jsonl",
        "visual_review.json",
    ):
        p = PREVIEW / name
        assert p.exists(), f"missing preview file: {p}"


def test_preview_index_is_japanese():
    html_text = (PREVIEW / "index.html").read_text(encoding="utf-8")
    for token in [
        "MVP-1 王道判定プレビュー",
        "観測専用",
        "READY通知不可",
        "売買未使用",
        "王道判定画面",
        "AI画面レビュー",
        "詳細ダッシュボード",
        "安全フラグ",
        "下書き要約",
    ]:
        assert token in html_text, f"index missing {token!r}"


def test_preview_index_uses_relative_urls():
    html_text = (PREVIEW / "index.html").read_text(encoding="utf-8")
    assert 'src="./decision_screen.png"' in html_text
    assert 'href="./decision_screen.html"' in html_text
    assert 'href="./dashboard.html"' in html_text
    assert 'href="./diagnostics.json"' in html_text
    assert 'href="./visual_review.json"' in html_text


def test_preview_does_not_enable_ready_or_notification():
    html_text = (PREVIEW / "index.html").read_text(encoding="utf-8")
    forbidden = [
        "READY通知可能",
        "本番通知ON",
        "売買可能",
        "自動売買",
        "発注",
        "broker connected",
        "live connected",
        "MVP-1 Observation Pipeline Preview",
        "SAFE: offline analysis only",
        "Open full dashboard.html",
    ]
    for token in forbidden:
        assert token not in html_text, f"index must not contain {token!r}"


def test_preview_dashboard_is_japanese_localised():
    html_text = (PREVIEW / "dashboard.html").read_text(encoding="utf-8")
    assert "MVP-1 王道判定ダッシュボード" in html_text
    assert "観測専用" in html_text
    assert "下書き分析" in html_text
    assert "FX Monitor Draft Review Dashboard" not in html_text
    assert "offline artifact / not used for READY" not in html_text


def test_preview_decision_screen_html_contains_geometry_classes():
    html_text = (PREVIEW / "decision_screen.html").read_text(encoding="utf-8")
    for token in [
        "rr-screen",
        "rr-safety-header",
        "rr-main",
        "rr-chart-panel",
        "rr-checklist-panel",
        "rr-ai-visual-review",
        "rr-wave-skeleton-line",
        "rr-pivot-dot",
        "rr-pivot-label",
        "rr-wnl-line",
        "rr-wsl-line",
        "rr-wtp-line",
        "rr-structural-trendline",
        "rr-sr-zone",
        "rr-safety-watermark",
    ]:
        assert token in html_text, f"decision_screen missing {token!r}"


def test_preview_decision_screen_png_is_populated():
    png = PREVIEW / "decision_screen.png"
    assert png.stat().st_size > 50_000


def test_preview_visual_review_safety_flags():
    data = json.loads((PREVIEW / "visual_review.json").read_text(encoding="utf-8"))
    assert data["used_for_ready"] is False
    assert data["used_for_notification"] is False
    assert data["used_for_trading"] is False
    assert "providers" in data
    assert "openai" in data["providers"]
    assert "claude" in data["providers"]


def test_preview_diagnostics_safety_flags():
    data = json.loads((PREVIEW / "diagnostics.json").read_text(encoding="utf-8"))
    assert data["decision"]["level"] == "SUPPRESSED"
    assert data["safety"]["ready_allowed"] is False
    assert data["safety"]["dispatch_called"] is False
    assert data["draft"]["observation_only"] is True
    assert data["draft"]["entry_status"] == "HOLD"
    assert data["draft"]["p0_pass"] is False
    assert data["draft"]["rich_draft"]["ready_eligible"] is False
    assert data["draft"]["rich_draft"]["p0_pass"] is False


def test_preview_review_report_safety_flags():
    data = json.loads((PREVIEW / "review_report.json").read_text(encoding="utf-8"))
    assert data["safety"]["used_for_ready"] is False
    assert data["safety"]["used_for_notification"] is False
    assert data["safety"]["offline_analysis_only"] is True


def test_preview_has_no_local_absolute_paths():
    for name in (
        "index.html",
        "decision_screen.html",
        "dashboard.html",
        "diagnostics.json",
        "review_log.jsonl",
        "review_report.md",
        "review_report.json",
        "visual_review.json",
    ):
        text = (PREVIEW / name).read_text(encoding="utf-8")
        assert "/home/user" not in text, f"{name} contains /home/user"
        assert "/home/runner" not in text, f"{name} contains /home/runner"
        assert "/tmp/" not in text, f"{name} contains /tmp/"


def test_preview_chart_pattern_is_populated():
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
