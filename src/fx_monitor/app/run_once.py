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
from ..logging import append_review_log, write_diagnostics
from ..notify.console_notifier import ConsoleNotifier
from ..notify.notifier import CooldownTracker, decide, dispatch
from ..render.chart_card_renderer import render_royal_road_notification_card
from ..render.draft_chart_renderer import render_draft_rich_chart


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
      4. if FX_MONITOR_REVIEW_DRAFT_WITH_AI=true, call OpenAI / Claude
         reviewers and append a JSONL summary record. The review result
         does NOT influence the notification decision.
      5. always report Decision SUPPRESSED.

    Notification dispatch is never called from this path. AI's view on
    the draft is captured purely for offline study.
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

    rich = draft.rich_draft or {}
    rich_pattern = (rich.get("pattern_levels_draft") or {}).get("pattern_kind")
    rich_wave_lines = rich.get("wave_derived_lines_draft") or []
    rich_structural_total = (
        (rich.get("structural_lines_draft") or {}).get("counts") or {}
    ).get("total", 0)
    rich_trendlines = (
        (rich.get("trendline_context_draft") or {}).get("selected_trendlines_top3") or []
    )
    print(
        "Rich draft: "
        f"pattern={rich_pattern} "
        f"wave_lines={len(rich_wave_lines)} "
        f"structural_lines={rich_structural_total} "
        f"trendlines={len(rich_trendlines)} "
        f"ready_eligible={rich.get('ready_eligible')}"
    )

    draft_chart_path: str | None = None
    if _env_truthy("FX_MONITOR_RENDER_DRAFT_CHART"):
        chart_out = os.environ.get(
            "FX_MONITOR_DRAFT_CHART_PATH", "out/draft_chart.png"
        )
        try:
            rendered = render_draft_rich_chart(
                rich_draft=rich,
                out_path=chart_out,
                title=(
                    f"{snapshot.symbol} {snapshot.timeframe} "
                    f"rich draft (observation only)"
                ),
            )
            draft_chart_path = str(rendered)
            print(f"Draft chart: {draft_chart_path}")
        except Exception as exc:
            # Renderer is already defensive, but be paranoid: never let
            # chart rendering bring down the workflow.
            print(f"Draft chart: skipped ({type(exc).__name__})")

    case = build_monitor_case_from_draft_payload(draft)
    rule = evaluate_monitor_case(case)
    print(f"Rule: {rule.verdict} {rule.bias}")

    review_draft = _env_truthy("FX_MONITOR_REVIEW_DRAFT_WITH_AI")
    diag_path = os.environ.get("FX_MONITOR_DIAGNOSTICS_PATH", "out/diagnostics.json")

    openai_review = None
    claude_review = None
    cmp_outcome = None

    if not review_draft:
        print("OpenAI: (not run)")
        print("Claude: (not run)")
        print("Compare: INSUFFICIENT")
        print("Decision: SUPPRESSED (draft payload only; READY disabled)")
        _write_market_draft_diagnostics(
            diag_path=diag_path,
            snapshot=snapshot,
            draft=draft,
            rule=rule,
            review_draft=False,
            openai_review=None,
            claude_review=None,
            cmp_outcome=None,
            draft_chart_path=draft_chart_path,
        )
        return 0

    # --- Draft AI review (observation only) ---
    pack = load_knowledge_pack()
    if _env_truthy("AI_USE_MOCK"):
        openai_review = MockReviewer(provider="openai").review(case)
        claude_review = MockReviewer(provider="claude").review(case)
    else:
        openai_review = OpenAIReviewer(pack).review(case)
        claude_review = ClaudeReviewer(pack).review(case)

    cmp_outcome = compare(openai_review, claude_review)

    print(f"OpenAI: {openai_review.verdict} {openai_review.bias}")
    print(f"Claude: {claude_review.verdict} {claude_review.bias}")
    print(f"Compare: {cmp_outcome.result}")
    print("Decision: SUPPRESSED (draft AI review is observation-only)")

    log_path = os.environ.get("FX_MONITOR_REVIEW_LOG_PATH", "out/review_log.jsonl")
    append_review_log(
        path=log_path,
        record={
            "mode": "draft_ai_review",
            "symbol": snapshot.symbol,
            "timeframe": snapshot.timeframe,
            "source": snapshot.source,
            "candles": len(snapshot.candles),
            "pivots": len(draft.pivots),
            "rough_pattern": rough_pattern,
            "zones": len(zones),
            "rule": {
                "verdict": rule.verdict,
                "bias": rule.bias,
                "reasons": rule.reasons,
            },
            "openai": {
                "verdict": openai_review.verdict,
                "bias": openai_review.bias,
                "confidence": openai_review.confidence,
                "reasons": openai_review.reasons[:5],
                "missing": openai_review.missing[:10],
                "disagreements": openai_review.disagreements[:10],
            },
            "claude": {
                "verdict": claude_review.verdict,
                "bias": claude_review.bias,
                "confidence": claude_review.confidence,
                "reasons": claude_review.reasons[:5],
                "missing": claude_review.missing[:10],
                "disagreements": claude_review.disagreements[:10],
            },
            "compare": {
                "result": cmp_outcome.result,
                "notes": cmp_outcome.notes[:5],
            },
            "decision": "SUPPRESSED",
            "safety": {
                "observation_only": True,
                "used_in_final_action": False,
                "ready_allowed": False,
            },
        },
    )
    print(f"Review log: {log_path}")

    _write_market_draft_diagnostics(
        diag_path=diag_path,
        snapshot=snapshot,
        draft=draft,
        rule=rule,
        review_draft=True,
        openai_review=openai_review,
        claude_review=claude_review,
        cmp_outcome=cmp_outcome,
        draft_chart_path=draft_chart_path,
    )
    return 0


def _write_market_draft_diagnostics(
    *,
    diag_path: str,
    snapshot,
    draft,
    rule,
    review_draft: bool,
    openai_review,
    claude_review,
    cmp_outcome,
    draft_chart_path: str | None = None,
) -> None:
    """Emit the per-run diagnostics JSON. Always called from feed mode."""
    zones = draft.rough_support_resistance.get("selected_level_zones_top5") or []
    rough_pattern = draft.rough_wave_context.get("rough_pattern_kind")
    rich = draft.rich_draft or {}
    rich_pattern = rich.get("pattern_levels_draft") or {}
    rich_structural = rich.get("structural_lines_draft") or {}
    rich_sr = rich.get("support_resistance_v2_draft") or {}
    rich_trend = rich.get("trendline_context_draft") or {}
    rich_checklist = rich.get("royal_road_procedure_checklist_draft") or {}
    diagnostics = {
        "mode": "market_draft",
        "feed": {
            "source": snapshot.source,
            "symbol": snapshot.symbol,
            "timeframe": snapshot.timeframe,
            "candles": len(snapshot.candles),
            "last_close": snapshot.last_close,
            "warnings": list(snapshot.warnings),
        },
        "draft": {
            "pivots": len(draft.pivots),
            "rough_pattern": rough_pattern,
            "zones": len(zones),
            "warnings": list(draft.warnings),
            "observation_only": draft.observation_only,
            "used_in_final_action": draft.used_in_final_action,
            "entry_status": draft.entry_plan.get("entry_status"),
            "p0_pass": draft.royal_road_procedure_checklist.get("p0_pass"),
            "rich_draft": {
                "schema_version": rich.get("schema_version"),
                "ready_eligible": rich.get("ready_eligible"),
                "pattern_kind": rich_pattern.get("pattern_kind"),
                "pattern_available": rich_pattern.get("available"),
                "wave_lines": len(rich.get("wave_derived_lines_draft") or []),
                "structural_lines": (rich_structural.get("counts") or {}).get("total", 0),
                "sr_zones": len(rich_sr.get("selected_level_zones_top5") or []),
                "trendlines": len(rich_trend.get("selected_trendlines_top3") or []),
                "p0_pass": rich_checklist.get("p0_pass"),
                "chart_path": draft_chart_path,
                "chart_rendered": draft_chart_path is not None,
            },
        },
        "rule": {
            "verdict": rule.verdict,
            "bias": rule.bias,
            "reasons": list(rule.reasons),
        },
        "ai": {
            "review_draft_with_ai": review_draft,
            "openai": {
                "enabled": os.getenv("OPENAI_ENABLED", "false"),
                "verdict": openai_review.verdict if openai_review else "not_run",
                "bias": openai_review.bias if openai_review else "none",
                "reasons": openai_review.reasons[:5] if openai_review else [],
                "missing": openai_review.missing[:10] if openai_review else [],
            },
            "claude": {
                "enabled": os.getenv("ANTHROPIC_ENABLED", "false"),
                "verdict": claude_review.verdict if claude_review else "not_run",
                "bias": claude_review.bias if claude_review else "none",
                "reasons": claude_review.reasons[:5] if claude_review else [],
                "missing": claude_review.missing[:10] if claude_review else [],
            },
            "compare": {
                "result": cmp_outcome.result if cmp_outcome else "INSUFFICIENT",
            },
        },
        "decision": {
            "level": "SUPPRESSED",
            "reason": "draft payload only; READY disabled",
        },
        "safety": {
            "ready_allowed": False,
            "dispatch_called": False,
            "dry_run": os.getenv("DRY_RUN", "true"),
        },
    }
    write_diagnostics(path=diag_path, data=diagnostics)
    print(f"Diagnostics: {diag_path}")


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
