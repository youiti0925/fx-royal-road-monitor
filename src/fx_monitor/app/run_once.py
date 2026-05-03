"""Run the monitor pipeline a single time (used by CI dry-run and CLI smoke).

Two input modes:

- Demo mode (default): synthetic ChartPayload built in-process. Useful for
  smoke-testing without any data feed.
- Fixture mode: load a saved royal-road payload JSON from
  ``FX_MONITOR_FIXTURE_PATH`` and adapt it to a MonitorCase. Used by tests
  and by anyone replaying a captured case.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..adapters import build_monitor_case_from_royal_road_payload
from ..ai.claude_reviewer import ClaudeReviewer
from ..ai.mock_reviewer import MockReviewer
from ..ai.openai_reviewer import OpenAIReviewer
from ..core.compare import compare
from ..core.models import (
    CalendarInfo,
    ChartPayload,
    HtfContext,
    LtfContext,
    MonitorCase,
    TriggerInfo,
)
from ..core.rule_engine import evaluate, evaluate_monitor_case
from ..knowledge.loader import load_knowledge_pack
from ..notify.console_notifier import ConsoleNotifier
from ..notify.notifier import CooldownTracker, decide, dispatch


def _demo_payload() -> ChartPayload:
    return ChartPayload(
        symbol=os.environ.get("DEMO_SYMBOL", "USDJPY"),
        timeframe=os.environ.get("DEMO_TIMEFRAME", "M5"),
        timestamp_utc=datetime.now(tz=timezone.utc),
        htf=HtfContext(h4_trend="up", d1_trend="up", key_levels=[155.20, 154.80]),
        ltf=LtfContext(
            structure="HH-HL",
            last_swing_high=155.10,
            last_swing_low=154.90,
            atr_14=0.12,
        ),
        trigger=TriggerInfo(type="breakout", occurred=True),
        calendar=CalendarInfo(high_impact_within_15min=False),
    )


def load_fixture_case(path: str | Path) -> MonitorCase:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return build_monitor_case_from_royal_road_payload(raw)


def main(argv: list[str] | None = None) -> int:
    pack = load_knowledge_pack()

    fixture_path = os.environ.get("FX_MONITOR_FIXTURE_PATH")
    if fixture_path:
        case = load_fixture_case(fixture_path)
        payload = case.chart_payload
        rule = evaluate_monitor_case(case)
    else:
        payload = _demo_payload()
        case = None
        rule = evaluate(payload)

    use_mock = os.environ.get("AI_USE_MOCK", "false").lower() in ("1", "true", "yes")
    if use_mock:
        openai_r = MockReviewer(provider="openai").review(payload)
        claude_r = MockReviewer(provider="claude").review(payload)
    else:
        # Reviewers self-gate on OPENAI_ENABLED / ANTHROPIC_ENABLED and on the
        # presence of API keys, returning UNKNOWN when not usable. We always
        # call review() so the reason surfaces in the summary line.
        review_target = case if case is not None else payload
        openai_r = OpenAIReviewer(pack).review(review_target)
        claude_r = ClaudeReviewer(pack).review(review_target)

    cmp_outcome = compare(openai_r, claude_r)
    cooldown = CooldownTracker()
    decision = decide(payload, rule, cmp_outcome, openai_r, claude_r, cooldown)

    _print_summary(rule, openai_r, claude_r, cmp_outcome, decision)
    dispatch(decision, [ConsoleNotifier()])
    return 0


def _summarize_reviewer(label: str, r) -> str:
    if r is None:
        return f"{label}: (not run)"
    reason = ""
    if r.missing:
        reason = f" reason={r.missing[0]}"
    elif r.reasons:
        reason = f" reason={r.reasons[0]}"
    return f"{label}: {r.verdict} {r.bias}{reason}"


def _print_summary(rule, openai_r, claude_r, cmp_outcome, decision) -> None:
    print(f"Rule: {rule.verdict} {rule.bias}")
    print(_summarize_reviewer("OpenAI", openai_r))
    print(_summarize_reviewer("Claude", claude_r))
    print(f"Compare: {cmp_outcome.result}")
    print(f"Decision: {decision.level} ({decision.reason})")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
