from __future__ import annotations

from pathlib import Path

PLAN = Path("docs/DRAFT_TO_RICH_PROMOTION_PLAN.md")
README = Path("README.md")
RUNBOOK = Path("docs/RUNBOOK_SCHEDULED_DRAFT_REVIEW.md")


def test_promotion_plan_exists():
    assert PLAN.exists(), f"missing plan: {PLAN}"


def test_promotion_plan_pins_no_ready_from_draft():
    text = PLAN.read_text(encoding="utf-8")

    for token in [
        "draft mode READY = impossible",
        "entry_plan.entry_status = HOLD",
        "royal_road_procedure_checklist.p0_pass = false",
        "Decision = SUPPRESSED",
        "No phase may skip directly from rough OHLC pivots to READY",
    ]:
        assert token in text, f"plan missing required token {token!r}"


def test_promotion_plan_defines_phases_in_order():
    text = PLAN.read_text(encoding="utf-8")

    expected = [
        "Phase P0: Observation-only draft",
        "Phase P1: Rich structure draft",
        "Phase P2: Visual validation",
        "Phase P3: Backtest-only candidate evaluation",
        "Phase P4: WAIT-only production monitor",
        "Phase P5: READY-eligible shadow mode",
        "Phase P6: READY notification approval gate",
    ]

    last = -1
    for token in expected:
        idx = text.find(token)
        assert idx >= 0, f"missing {token}"
        assert idx > last, f"phase out of order: {token}"
        last = idx


def test_promotion_plan_forbids_trading_and_broker_shortcuts():
    text = PLAN.read_text(encoding="utf-8")

    for token in [
        "OANDA live trading",
        "paper broker",
        "auto trading",
        "place order",
        "broker API key storage",
        "separate safety review",
    ]:
        assert token in text, f"plan missing forbidden-list token {token!r}"


def test_promotion_plan_pins_ready_approval_gate():
    text = PLAN.read_text(encoding="utf-8")
    assert "explicit approval" in text
    assert "manual approval recorded in docs" in text
    assert "no auto trading" in text
    assert "no order execution" in text
    assert "no broker connection" in text


def test_readme_and_runbook_link_to_promotion_plan():
    assert "docs/DRAFT_TO_RICH_PROMOTION_PLAN.md" in README.read_text(encoding="utf-8")
    assert "DRAFT_TO_RICH_PROMOTION_PLAN.md" in RUNBOOK.read_text(encoding="utf-8")
