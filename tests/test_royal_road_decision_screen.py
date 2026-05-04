from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fx_monitor.analysis.rich_draft import build_rich_draft
from fx_monitor.core.models import PivotPoint
from fx_monitor.render.royal_road_decision_screen import (
    build_royal_road_decision_screen_html,
    render_royal_road_decision_screen_png,
)

pytest.importorskip("matplotlib")


def _p(index: int, price: float, kind: str) -> PivotPoint:
    return PivotPoint(
        index=index,
        timestamp_utc=datetime(2026, 5, 4, tzinfo=timezone.utc),
        price=price,
        kind=kind,
        strength=2,
    )


def _dt_rich() -> dict:
    return build_rich_draft(
        pivots=[
            _p(5, 1.1050, "HIGH"),
            _p(10, 1.1000, "LOW"),
            _p(15, 1.1048, "HIGH"),
            _p(20, 1.0980, "LOW"),
        ],
        rough_support_resistance={
            "selected_level_zones_top5": [
                {"id": "RZ1", "price": 1.1000, "price_low": 1.0998, "price_high": 1.1002}
            ],
            "warnings": [],
        },
    )


def _diagnostics() -> dict:
    return {
        "feed": {"symbol": "EURUSD=X", "timeframe": "M5"},
        "decision": {"level": "SUPPRESSED"},
        "safety": {"ready_allowed": False, "dispatch_called": False},
        "draft": {
            "rich_draft": {
                "ready_eligible": False,
                "p0_pass": False,
                "pattern_kind": "possible_double_top",
            }
        },
    }


def test_decision_screen_html_is_japanese():
    html_text = build_royal_road_decision_screen_html(
        rich_draft=_dt_rich(),
        diagnostics=_diagnostics(),
    )
    for token in [
        "MVP-1 王道判定プレビュー",
        "観測専用",
        "READY通知不可",
        "売買未使用",
        "王道手順チェック",
        "下書きチャート",
        "波形認識",
        "Wライン",
        "トレンドライン",
        "AI画面レビュー",
    ]:
        assert token in html_text, f"decision screen missing {token!r}"


def test_decision_screen_contains_chart_geometry_classes():
    html_text = build_royal_road_decision_screen_html(
        rich_draft=_dt_rich(),
        diagnostics=_diagnostics(),
    )
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
        assert token in html_text, f"decision screen missing class {token!r}"


def test_decision_screen_html_does_not_claim_ready():
    html_text = build_royal_road_decision_screen_html(
        rich_draft=_dt_rich(),
        diagnostics=_diagnostics(),
    )
    forbidden = [
        "READY通知可能",
        "本番通知ON",
        "売買可能",
        "自動売買",
        "発注",
        "broker connected",
        "live connected",
    ]
    for token in forbidden:
        assert token not in html_text


def test_decision_screen_png_is_created(tmp_path):
    out = tmp_path / "decision.png"
    path = render_royal_road_decision_screen_png(
        rich_draft=_dt_rich(),
        diagnostics=_diagnostics(),
        out_path=out,
    )
    assert path.exists()
    assert path.stat().st_size > 50_000


def test_decision_screen_png_falls_back_for_empty_rich_draft(tmp_path):
    out = tmp_path / "empty.png"
    path = render_royal_road_decision_screen_png(
        rich_draft={},
        diagnostics={"decision": {"level": "SUPPRESSED"},
                     "safety": {"ready_allowed": False, "dispatch_called": False}},
        out_path=out,
    )
    assert path.exists()
    # Even empty rich_draft must produce a real PNG, not a 1px placeholder.
    assert path.stat().st_size > 5_000


def test_decision_screen_html_renders_visual_review_block():
    html_text = build_royal_road_decision_screen_html(
        rich_draft=_dt_rich(),
        diagnostics=_diagnostics(),
        visual_review={
            "providers": {
                "openai": {"verdict": "UNKNOWN", "summary_ja": "API無効"},
                "claude": {"verdict": "UNKNOWN", "summary_ja": "API無効"},
            },
            "combined_verdict": "UNKNOWN",
        },
    )
    assert "OpenAI" in html_text
    assert "Claude" in html_text
    assert "UNKNOWN" in html_text
    assert "総合判定" in html_text
