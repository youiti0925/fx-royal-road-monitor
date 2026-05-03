from __future__ import annotations

import json
from pathlib import Path

import pytest

from fx_monitor.adapters import build_monitor_case_from_royal_road_payload
from fx_monitor.ai.mock_reviewer import MockReviewer
from fx_monitor.core.compare import compare
from fx_monitor.core.rule_engine import evaluate_monitor_case
from fx_monitor.notify.notifier import CooldownTracker, decide
from fx_monitor.render.chart_card_renderer import render_royal_road_notification_card

pytest.importorskip("matplotlib")

FIXTURES = Path(__file__).parent / "fixtures"


def _case(name: str):
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return build_monitor_case_from_royal_road_payload(raw)


def _make_inputs(name: str):
    case = _case(name)
    rule = evaluate_monitor_case(case)
    openai = MockReviewer(provider="openai").review(case.chart_payload)
    claude = MockReviewer(provider="claude").review(case.chart_payload)
    cmp_outcome = compare(openai, claude)
    decision = decide(
        case.chart_payload,
        rule,
        cmp_outcome,
        openai,
        claude,
        CooldownTracker(),
        now=1000.0,
    )
    return case, rule, openai, claude, cmp_outcome, decision


def test_render_royal_road_notification_card_ready_fixture(tmp_path):
    case, rule, openai, claude, cmp_outcome, decision = _make_inputs(
        "royal_road_ready_sell_payload.json"
    )

    out = tmp_path / "card.png"
    path = render_royal_road_notification_card(
        case=case,
        rule=rule,
        openai_review=openai,
        claude_review=claude,
        compare_outcome=cmp_outcome,
        decision=decision,
        out_path=out,
    )

    assert path.exists()
    # Real PNG, not the 1-pixel placeholder. The placeholder is ~70 bytes.
    assert path.stat().st_size > 5000


def test_render_card_event_block_fixture(tmp_path):
    case, rule, openai, claude, cmp_outcome, decision = _make_inputs(
        "royal_road_event_block_payload.json"
    )

    out = tmp_path / "event_block_card.png"
    path = render_royal_road_notification_card(
        case=case,
        rule=rule,
        openai_review=openai,
        claude_review=claude,
        compare_outcome=cmp_outcome,
        decision=decision,
        out_path=out,
    )

    assert path.exists()
    assert path.stat().st_size > 5000


def test_render_card_wait_retest_fixture(tmp_path):
    case, rule, openai, claude, cmp_outcome, decision = _make_inputs(
        "royal_road_wait_retest_payload.json"
    )

    out = tmp_path / "wait_retest_card.png"
    path = render_royal_road_notification_card(
        case=case,
        rule=rule,
        openai_review=openai,
        claude_review=claude,
        compare_outcome=cmp_outcome,
        decision=decision,
        out_path=out,
    )

    assert path.exists()
    assert path.stat().st_size > 5000


def test_render_card_writes_to_nested_path(tmp_path):
    case, rule, openai, claude, cmp_outcome, decision = _make_inputs(
        "royal_road_ready_sell_payload.json"
    )

    out = tmp_path / "deep" / "nested" / "card.png"
    path = render_royal_road_notification_card(
        case=case,
        rule=rule,
        openai_review=openai,
        claude_review=claude,
        compare_outcome=cmp_outcome,
        decision=decision,
        out_path=out,
    )
    assert path.exists()
