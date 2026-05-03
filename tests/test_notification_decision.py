from __future__ import annotations

from fx_monitor.core.compare import compare
from fx_monitor.core.models import ReviewResult, RuleResult
from fx_monitor.core.rule_engine import evaluate
from fx_monitor.notify.notifier import CooldownTracker, decide


def _pass_review(provider: str, bias: str = "long") -> ReviewResult:
    return ReviewResult(provider=provider, verdict="PASS", bias=bias, confidence=0.8)


def test_ready_when_rule_pass_and_agree_pass(passing_payload):
    rule = evaluate(passing_payload)
    assert rule.verdict == "PASS"
    o = _pass_review("openai")
    c = _pass_review("claude")
    cmp_outcome = compare(o, c)
    assert cmp_outcome.result == "AGREE_PASS"

    cooldown = CooldownTracker()
    decision = decide(passing_payload, rule, cmp_outcome, o, c, cooldown, now=1000.0)
    assert decision.level == "READY"
    assert "READY" in decision.title


def test_cooldown_suppresses_second_ready(passing_payload):
    rule = evaluate(passing_payload)
    cmp_outcome = compare(_pass_review("openai"), _pass_review("claude"))
    cooldown = CooldownTracker()

    first = decide(passing_payload, rule, cmp_outcome, None, None, cooldown, now=1000.0)
    second = decide(passing_payload, rule, cmp_outcome, None, None, cooldown, now=1100.0)

    assert first.level == "READY"
    assert second.level == "SUPPRESSED"
    assert "cooldown" in second.reason.lower()


def test_calendar_guard_suppresses(passing_payload):
    payload = passing_payload.model_copy(
        update={"calendar": passing_payload.calendar.model_copy(update={"high_impact_within_15min": True})}
    )
    rule = evaluate(payload)
    cmp_outcome = compare(_pass_review("openai"), _pass_review("claude"))
    decision = decide(payload, rule, cmp_outcome, None, None, CooldownTracker(), now=1000.0)
    assert decision.level == "SUPPRESSED"
    assert "calendar" in decision.reason.lower()


def test_disagree_does_not_become_ready(passing_payload):
    rule = evaluate(passing_payload)
    o = ReviewResult(provider="openai", verdict="PASS", bias="long", confidence=0.7)
    c = ReviewResult(provider="claude", verdict="PASS", bias="short", confidence=0.7)
    cmp_outcome = compare(o, c)
    decision = decide(passing_payload, rule, cmp_outcome, o, c, CooldownTracker(), now=1000.0)
    assert decision.level != "READY"


def test_insufficient_ai_reviews_are_suppressed_not_watch(passing_payload):
    rule = evaluate(passing_payload)
    assert rule.verdict == "PASS"

    # One reviewer UNKNOWN -> compare is INSUFFICIENT.
    o = ReviewResult(provider="openai", verdict="UNKNOWN", bias="none", confidence=0.0)
    c = ReviewResult(provider="claude", verdict="PASS", bias="long", confidence=0.7)
    cmp_outcome = compare(o, c)
    assert cmp_outcome.result == "INSUFFICIENT"

    decision = decide(passing_payload, rule, cmp_outcome, o, c, CooldownTracker(), now=1000.0)
    assert decision.level == "SUPPRESSED"
    assert decision.should_dispatch is False
    assert "insufficient" in decision.reason.lower()


def test_insufficient_with_both_unknown_is_suppressed(passing_payload):
    rule = evaluate(passing_payload)
    o = ReviewResult(provider="openai", verdict="UNKNOWN", bias="none")
    c = ReviewResult(provider="claude", verdict="UNKNOWN", bias="none")
    cmp_outcome = compare(o, c)
    assert cmp_outcome.result == "INSUFFICIENT"

    decision = decide(passing_payload, rule, cmp_outcome, o, c, CooldownTracker(), now=1000.0)
    assert decision.level == "SUPPRESSED"
    assert decision.should_dispatch is False


def test_agree_pass_still_ready_after_insufficient_change(passing_payload):
    """Regression guard: the INSUFFICIENT->SUPPRESSED short-circuit must not
    block an actual AGREE_PASS path."""
    rule = evaluate(passing_payload)
    cmp_outcome = compare(_pass_review("openai"), _pass_review("claude"))
    assert cmp_outcome.result == "AGREE_PASS"

    decision = decide(passing_payload, rule, cmp_outcome, None, None, CooldownTracker(), now=1000.0)
    assert decision.level == "READY"
    assert decision.should_dispatch is True


def test_block_when_calendar_event_in_rule_engine():
    from datetime import datetime, timezone

    from fx_monitor.core.models import (
        CalendarInfo,
        ChartPayload,
        HtfContext,
        LtfContext,
        TriggerInfo,
    )

    payload = ChartPayload(
        symbol="USDJPY",
        timeframe="M5",
        timestamp_utc=datetime(2026, 5, 3, tzinfo=timezone.utc),
        htf=HtfContext(h4_trend="up", d1_trend="up"),
        ltf=LtfContext(structure="HH-HL", last_swing_high=2, last_swing_low=1, atr_14=0.1),
        trigger=TriggerInfo(type="breakout", occurred=True),
        calendar=CalendarInfo(high_impact_within_15min=True),
    )
    rule: RuleResult = evaluate(payload)
    assert rule.verdict == "BLOCK"
