from __future__ import annotations

from pathlib import Path

import pytest

from fx_monitor.ai.decision_screen_spec_compare import compare_decision_screen_specs
from fx_monitor.ai.decision_screen_spec_schema import safe_unknown_spec
from fx_monitor.render.royal_road_decision_screen import (
    build_royal_road_decision_screen_html,
    render_royal_road_decision_screen_png,
)

pytest.importorskip("matplotlib")


def _spec(provider: str, lines=None, points=None, side="SELL", status="WAIT_BREAKOUT"):
    return {
        "schema_version": "ai_decision_screen_spec_v1",
        "provider": provider,
        "observation_only": True,
        "used_for_ready": False,
        "used_for_notification": False,
        "used_for_trading": False,
        "symbol": "EURUSD=X",
        "timeframe": "M5",
        "side": side,
        "final_status": status,
        "pattern_label_ja": "ダブルトップ候補",
        "market_story_ja": "上昇後にネックラインを試す展開",
        "lines": lines or [],
        "points": points or [],
        "zones": [],
        "procedure_steps": [
            {"key": "wave_pattern", "label_ja": "波形認識", "status": "WAIT", "result_ja": ""},
            {"key": "neckline", "label_ja": "ネックライン", "status": "WAIT", "result_ja": ""},
        ],
        "summary_ja": f"{provider} による観測用",
    }


def _populated_specs():
    line_neckline = {
        "id": "L1",
        "label": "WNL",
        "kind": "neckline",
        "role": "entry_trigger",
        "price": 1.1000,
        "anchor_points": ["NL"],
        "confidence": 0.6,
        "reason_ja": "P1とP2の中間にNL",
    }
    point_p1 = {"id": "P1", "label": "P1", "role": "high",
                "index": 5, "price": 1.1050, "reason_ja": "1つ目の高値"}
    point_p2 = {"id": "P2", "label": "P2", "role": "high",
                "index": 15, "price": 1.1048, "reason_ja": "2つ目の高値"}
    o = _spec("openai", lines=[{**line_neckline, "id": "OL1"}],
              points=[point_p1, point_p2])
    c = _spec("claude", lines=[{**line_neckline, "id": "CL1"}],
              points=[point_p1, point_p2])
    return o, c


def test_renderer_html_paints_only_ai_lines():
    o, c = _populated_specs()
    cmp_out = compare_decision_screen_specs(openai_spec=o, claude_spec=c)
    html_text = build_royal_road_decision_screen_html(
        openai_spec=o, claude_spec=c, comparison=cmp_out, market_analysis_pack={}
    )

    # AI-authored lines + points show up.
    assert "OL1" not in html_text  # internal ids are not rendered as text
    assert "WNL" in html_text  # human label IS rendered
    assert "P1" in html_text
    assert "P2" in html_text


def test_renderer_html_does_not_invent_lines_when_specs_unknown():
    o = safe_unknown_spec(provider="openai", symbol="EURUSD=X",
                          timeframe="M5", reason="openai_disabled").model_dump(mode="json")
    c = safe_unknown_spec(provider="claude", symbol="EURUSD=X",
                          timeframe="M5", reason="anthropic_disabled").model_dump(mode="json")
    cmp_out = compare_decision_screen_specs(openai_spec=o, claude_spec=c)
    html_text = build_royal_road_decision_screen_html(
        openai_spec=o, claude_spec=c, comparison=cmp_out, market_analysis_pack={}
    )

    # No AI-authored lines means the renderer must not invent any.
    assert "WNL" not in html_text  # neither openai nor claude authored it
    assert "AIによる王道判定画面が未生成" in html_text


def test_renderer_html_is_japanese_and_shows_provider_breakdown():
    o, c = _populated_specs()
    cmp_out = compare_decision_screen_specs(openai_spec=o, claude_spec=c)
    html_text = build_royal_road_decision_screen_html(
        openai_spec=o, claude_spec=c, comparison=cmp_out, market_analysis_pack={}
    )
    for token in [
        "AI生成 王道判定画面",
        "観測専用",
        "READY通知不可",
        "売買未使用",
        "OpenAI案",
        "Claude案",
        "二者比較",
        "一致",
        "不一致",
        "王道手順チェック",
    ]:
        assert token in html_text, f"renderer missing {token!r}"


def test_renderer_html_contains_geometry_classes():
    o, c = _populated_specs()
    cmp_out = compare_decision_screen_specs(openai_spec=o, claude_spec=c)
    html_text = build_royal_road_decision_screen_html(
        openai_spec=o, claude_spec=c, comparison=cmp_out, market_analysis_pack={}
    )
    for cls in [
        "rr-screen",
        "rr-safety-header",
        "rr-main",
        "rr-chart-panel",
        "rr-checklist-panel",
        "rr-pivot-dot",
        "rr-pivot-label",
        "rr-wave-skeleton-line",
        "rr-wnl-line",
        "rr-wsl-line",
        "rr-wtp-line",
        "rr-structural-trendline",
        "rr-sr-zone",
        "rr-safety-watermark",
    ]:
        assert cls in html_text, f"renderer missing class {cls!r}"


def test_renderer_html_does_not_claim_ready_or_trading():
    o, c = _populated_specs()
    cmp_out = compare_decision_screen_specs(openai_spec=o, claude_spec=c)
    html_text = build_royal_road_decision_screen_html(
        openai_spec=o, claude_spec=c, comparison=cmp_out, market_analysis_pack={}
    )
    forbidden = [
        "READY通知可能",
        "本番通知ON",
        "売買可能",
        "broker connected",
        "live connected",
    ]
    for token in forbidden:
        assert token not in html_text


def test_renderer_png_is_produced(tmp_path):
    o, c = _populated_specs()
    cmp_out = compare_decision_screen_specs(openai_spec=o, claude_spec=c)
    out = tmp_path / "ds.png"
    path = render_royal_road_decision_screen_png(
        openai_spec=o, claude_spec=c, comparison=cmp_out,
        market_analysis_pack={}, out_path=out,
    )
    assert path.exists()
    assert path.stat().st_size > 50_000


def test_renderer_png_handles_unknown_specs(tmp_path):
    o = safe_unknown_spec(provider="openai", symbol="EURUSD=X",
                          timeframe="M5", reason="openai_disabled").model_dump(mode="json")
    c = safe_unknown_spec(provider="claude", symbol="EURUSD=X",
                          timeframe="M5", reason="anthropic_disabled").model_dump(mode="json")
    cmp_out = compare_decision_screen_specs(openai_spec=o, claude_spec=c)
    out = tmp_path / "ds_unknown.png"
    path = render_royal_road_decision_screen_png(
        openai_spec=o, claude_spec=c, comparison=cmp_out,
        market_analysis_pack={}, out_path=out,
    )
    assert path.exists()
    # Even the placeholder PNG (matplotlib draws "AI not generated" message)
    # should easily exceed 5 KB.
    assert path.stat().st_size > 5_000
