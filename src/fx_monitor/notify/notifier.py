"""Notification decision + dispatch.

The decision (READY / WATCH / INFO / SUPPRESSED) is made here from the
deterministic inputs. AI cannot override calendar guard, cooldown, or DRY_RUN.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Protocol

from ..core.models import (
    ChartPayload,
    CompareOutcome,
    NotificationDecision,
    NotifyLevel,
    ReviewResult,
    RuleResult,
)


class NotifyBackend(Protocol):
    name: str

    def send(self, decision: NotificationDecision) -> bool: ...


def _cooldown_seconds() -> int:
    try:
        return int(os.environ.get("NOTIFY_COOLDOWN_SECONDS", "900"))
    except ValueError:
        return 900


def _is_dry_run() -> bool:
    return os.environ.get("DRY_RUN", "true").lower() in ("1", "true", "yes")


@dataclass
class CooldownTracker:
    """In-memory per-(symbol, timeframe) cooldown for READY notifications."""

    last_ready_at: dict[tuple[str, str], float] = field(default_factory=dict)

    def is_cooling_down(self, symbol: str, timeframe: str, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        last = self.last_ready_at.get((symbol, timeframe))
        if last is None:
            return False
        return (now - last) < _cooldown_seconds()

    def mark_ready(self, symbol: str, timeframe: str, now: float | None = None) -> None:
        self.last_ready_at[(symbol, timeframe)] = now if now is not None else time.time()


def decide(
    payload: ChartPayload,
    rule: RuleResult,
    compare_outcome: CompareOutcome,
    openai: ReviewResult | None,
    claude: ReviewResult | None,
    cooldown: CooldownTracker,
    now: float | None = None,
) -> NotificationDecision:
    """Single source of truth for whether to send a notification."""

    if payload.calendar.high_impact_within_15min:
        return NotificationDecision(
            level="SUPPRESSED",
            reason="High-impact calendar event within 15 minutes.",
        )

    if compare_outcome.result == "INSUFFICIENT":
        # AI dual review could not be completed (disabled / missing key /
        # SDK error / one returned UNKNOWN). Per policy, log to stdout via
        # the run_once summary but do not push any notification.
        return NotificationDecision(
            level="SUPPRESSED",
            reason="AI review insufficient; suppressing notification.",
        )

    if rule.verdict == "PASS" and compare_outcome.result == "AGREE_PASS":
        if cooldown.is_cooling_down(payload.symbol, payload.timeframe, now):
            return NotificationDecision(
                level="SUPPRESSED",
                reason="Within cooldown window for previous READY.",
            )
        cooldown.mark_ready(payload.symbol, payload.timeframe, now)
        title = f"READY {payload.symbol} {payload.timeframe} -> {compare_outcome.bias}"
        body = _format_ready_body(payload, rule, compare_outcome, openai, claude)
        return NotificationDecision(level="READY", reason="rule PASS + AGREE_PASS", title=title, body=body)

    if rule.verdict == "PASS":
        return NotificationDecision(
            level="WATCH",
            reason=f"Rule PASS but compare={compare_outcome.result}.",
            title=f"WATCH {payload.symbol} {payload.timeframe}",
            body=f"compare={compare_outcome.result} notes={compare_outcome.notes}",
        )

    if rule.verdict in ("WAIT", "WARN"):
        return NotificationDecision(
            level="INFO",
            reason=f"Rule {rule.verdict}.",
        )

    return NotificationDecision(level="SUPPRESSED", reason=f"Rule {rule.verdict}.")


def _format_ready_body(
    payload: ChartPayload,
    rule: RuleResult,
    compare_outcome: CompareOutcome,
    openai: ReviewResult | None,
    claude: ReviewResult | None,
) -> str:
    lines = [
        f"symbol={payload.symbol} timeframe={payload.timeframe}",
        f"timestamp_utc={payload.timestamp_utc.isoformat()}",
        f"rule.verdict={rule.verdict} bias={rule.bias}",
        f"rule.reasons={rule.reasons}",
        f"compare={compare_outcome.result} bias={compare_outcome.bias}",
    ]
    for r in (openai, claude):
        if r is not None:
            lines.append(
                f"{r.provider}: verdict={r.verdict} bias={r.bias} "
                f"confidence={r.confidence:.2f} reasons={r.reasons[:3]}"
            )
    return "\n".join(lines)


def dispatch(
    decision: NotificationDecision,
    backends: list[NotifyBackend],
) -> dict[str, bool]:
    """Dispatch a decision to all backends. Never raises; returns per-backend success."""
    if not decision.should_dispatch:
        return {}
    if _is_dry_run():
        # In dry-run we still let console-style backends print but skip remote ones.
        results: dict[str, bool] = {}
        for b in backends:
            if b.name == "console":
                results[b.name] = _safe_send(b, decision)
        return results
    return {b.name: _safe_send(b, decision) for b in backends}


def _safe_send(backend: NotifyBackend, decision: NotificationDecision) -> bool:
    try:
        return bool(backend.send(decision))
    except Exception:
        return False


__all__ = [
    "NotifyBackend",
    "CooldownTracker",
    "decide",
    "dispatch",
    "NotifyLevel",
]
