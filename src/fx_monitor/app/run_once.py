"""Run the monitor pipeline a single time (used by CI dry-run and CLI smoke).

Three input modes (checked in this order):

1. Fixture mode: ``FX_MONITOR_FIXTURE_PATH`` points at a saved royal-road
   payload JSON. The adapter builds a full :class:`MonitorCase` and the
   pipeline can produce READY.
2. Feed mode: ``FX_MONITOR_FEED`` selects ``csv`` / ``yahoo`` and we fetch
   a :class:`MarketSnapshot`. The royal-road rich payload is **not** built
   from raw OHLC yet, so this mode never produces READY — it only prints
   the snapshot for observation.
3. Demo mode (default): synthetic :class:`ChartPayload`. Useful for
   smoke-testing without any data source.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..adapters import (
    build_monitor_case_from_draft_payload,
    build_monitor_case_from_royal_road_payload,
)
from ..analysis import build_royal_road_draft_payload_from_snapshot
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
from ..data.feed_selector import load_market_snapshot_from_env
from ..knowledge.loader import load_knowledge_pack
from ..notify.console_notifier import ConsoleNotifier
from ..notify.notifier import CooldownTracker, decide, dispatch
from ..render.chart_card_renderer import render_royal_road_notification_card


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


def _run_market_draft_mode() -> int:
    """Feed mode: snapshot -> observation-only draft payload. Never READY.

    Pipeline:
      1. fetch MarketSnapshot from FX_MONITOR_FEED
      2. build a RoyalRoadDraftPayload (pivots + rough S/R + rough wave)
      3. wrap in MonitorCase and run evaluate_monitor_case()
      4. report Rule + (no AI) + INSUFFICIENT + SUPPRESSED

    AI reviewers are intentionally NOT called here: the draft is
    observation-only and must never feed a notification, so spending
    real API tokens on it would be wasteful.
    """
    snapshot = load_market_snapshot_from_env()
    print(
        "Market snapshot: "
        f"{snapshot.symbol} {snapshot.timeframe} "
        f"source={snapshot.source} "
        f"candles={len(snapshot.candles)} "
        f"last_close={snapshot.last_close}"
    )
    if snapshot.warnings:
        print("Market warnings: " + ", ".join(snapshot.warnings))

    draft = build_royal_road_draft_payload_from_snapshot(snapshot)
    zones = draft.rough_support_resistance.get("selected_level_zones_top5") or []
    rough_pattern = draft.rough_wave_context.get("rough_pattern_kind", "unknown")
    print(
        "Draft payload: "
        f"pivots={len(draft.pivots)} "
        f"rough_pattern={rough_pattern} "
        f"zones={len(zones)} "
        f"observation_only={draft.observation_only}"
    )

    case = build_monitor_case_from_draft_payload(draft)
    rule = evaluate_monitor_case(case)
    print(f"Rule: {rule.verdict} {rule.bias}")
    print("OpenAI: (not run)")
    print("Claude: (not run)")
    print("Compare: INSUFFICIENT")
    print(
        "Decision: SUPPRESSED "
        "(draft payload only; READY disabled)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    pack = load_knowledge_pack()

    fixture_path = os.environ.get("FX_MONITOR_FIXTURE_PATH")
    feed_env = os.environ.get("FX_MONITOR_FEED", "").lower()

    if fixture_path:
        case = load_fixture_case(fixture_path)
        payload = case.chart_payload
        rule = evaluate_monitor_case(case)
    elif feed_env in ("csv", "yahoo"):
        return _run_market_draft_mode()
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

    # Render the notification card (if requested + we have a MonitorCase) and
    # optionally attach its path to the decision so notification backends can
    # upload it. The card is rendered even when DRY_RUN=true so operators can
    # eyeball the artifact; only the actual remote send is suppressed by
    # ``dispatch()`` / DRY_RUN.
    rendered_card_path: str | None = None
    if (
        case is not None
        and _env_truthy("FX_MONITOR_RENDER_CARD")
    ):
        out_path = os.environ.get("FX_MONITOR_CARD_PATH", "out/notification_card.png")
        rendered_card_path = str(
            render_royal_road_notification_card(
                case=case,
                rule=rule,
                openai_review=openai_r,
                claude_review=claude_r,
                compare_outcome=cmp_outcome,
                decision=decision,
                out_path=out_path,
            )
        )
        attach = _env_truthy("FX_MONITOR_ATTACH_CARD", default="true")
        if attach:
            decision = decision.model_copy(update={"image_path": rendered_card_path})

    _print_summary(rule, openai_r, claude_r, cmp_outcome, decision)
    if rendered_card_path:
        print(f"Notification card: {rendered_card_path}")
        print(f"Attach card: {'yes' if decision.image_path else 'no'}")
    dispatch(decision, [ConsoleNotifier()])
    return 0


def _env_truthy(name: str, *, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() in ("1", "true", "yes")


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
