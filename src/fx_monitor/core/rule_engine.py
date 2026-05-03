"""Deterministic royal-road rule check.

This is the *non-AI* layer. It must reach a conclusion using only the payload,
without calling out to any model. The AI reviewers are advisory; this engine
plus compare.py + notifier.py form the final decision path.
"""

from __future__ import annotations

from typing import Any

from .models import Bias, ChartPayload, MonitorCase, RuleResult, Verdict


def _direction_from_htf(payload: ChartPayload) -> Bias:
    h4, d1 = payload.htf.h4_trend, payload.htf.d1_trend
    if h4 == "up" and d1 in ("up", "range"):
        return "long"
    if h4 == "down" and d1 in ("down", "range"):
        return "short"
    return "none"


def evaluate(payload: ChartPayload) -> RuleResult:
    """Map a payload to a (verdict, bias, reasons) tuple per knowledge pack §1–§2."""

    reasons: list[str] = []

    # 1. Calendar guard - hard block.
    if payload.calendar.high_impact_within_15min:
        return RuleResult(
            verdict="BLOCK",
            bias="none",
            reasons=["High-impact calendar event within 15 minutes."],
        )

    # 2. HTF alignment.
    bias = _direction_from_htf(payload)
    if bias == "none":
        reasons.append("HTF h4/d1 not aligned (range or conflicting).")
        return RuleResult(verdict="WARN", bias="none", reasons=reasons)
    reasons.append(f"HTF aligned: h4={payload.htf.h4_trend}, d1={payload.htf.d1_trend} -> {bias}.")

    # 3. LTF structure consistency.
    structure = payload.ltf.structure
    if structure == "broken":
        reasons.append("LTF structure broken.")
        return RuleResult(verdict="WARN", bias=bias, reasons=reasons)
    if structure == "range":
        reasons.append("LTF in range; royal road requires trending structure.")
        return RuleResult(verdict="WAIT", bias=bias, reasons=reasons)
    if bias == "long" and structure != "HH-HL":
        reasons.append("Bias=long but LTF is not HH-HL.")
        return RuleResult(verdict="WARN", bias=bias, reasons=reasons)
    if bias == "short" and structure != "LH-LL":
        reasons.append("Bias=short but LTF is not LH-LL.")
        return RuleResult(verdict="WARN", bias=bias, reasons=reasons)
    reasons.append(f"LTF structure consistent ({structure}).")

    # 4. Sanity on swings / ATR.
    if payload.ltf.atr_14 <= 0:
        return RuleResult(verdict="UNKNOWN", bias=bias, reasons=["ATR not available."])
    if payload.ltf.last_swing_high <= payload.ltf.last_swing_low:
        return RuleResult(
            verdict="UNKNOWN",
            bias=bias,
            reasons=["Swing high <= swing low; payload inconsistent."],
        )

    # 5. Trigger.
    if not payload.trigger.occurred or payload.trigger.type == "none":
        reasons.append("Trigger not yet occurred.")
        return RuleResult(verdict="WAIT", bias=bias, reasons=reasons)
    reasons.append(f"Trigger occurred: {payload.trigger.type}.")

    # All checks passed.
    return RuleResult(verdict="PASS", bias=bias, reasons=reasons)


def _step_status(checklist: dict[str, Any], key: str) -> str:
    for step in checklist.get("steps", []) or []:
        if isinstance(step, dict) and step.get("key") == key:
            return str(step.get("status") or "UNKNOWN").upper()
    return "UNKNOWN"


_REQUIRED_RICH_STEPS = (
    "wave_pattern",
    "wave_lines",
    "breakout_confirmed",
    "retest_confirmed",
    "confirmation_candle",
    "entry_price",
    "stop_price",
    "target_price",
    "rr_ok",
    "event_clear",
)


def evaluate_monitor_case(case: MonitorCase) -> RuleResult:
    """Deterministic rule check using the rich royal-road payload.

    Stricter than the legacy ChartPayload evaluator. PASS requires:
    - selected_entry_candidate / entry_plan status == READY
    - checklist.p0_pass is true
    - every P0 checklist step is PASS
    - parseable entry/stop/target/rr with rr >= 2.0
    - structurally valid price order for the side
    - event risk not BLOCK
    """
    payload = case.ai_payload
    ep = payload.get("entry_plan") or {}
    selected = payload.get("selected_entry_candidate") or {}
    checklist = payload.get("royal_road_procedure_checklist") or {}
    fs = payload.get("fundamental_sidebar") or {}

    status = str(selected.get("status") or ep.get("entry_status") or "HOLD").upper()
    side = str(selected.get("side") or ep.get("side") or "NEUTRAL").upper()

    bias: Bias
    if side == "BUY":
        bias = "long"
    elif side == "SELL":
        bias = "short"
    else:
        bias = "none"

    event_status = str(fs.get("event_risk_status") or "").upper()
    if event_status == "BLOCK" or _step_status(checklist, "event_clear") == "BLOCK":
        return RuleResult(
            verdict="BLOCK",
            bias="none",
            reasons=["Event risk BLOCK; no notification allowed."],
        )

    if status != "READY":
        return RuleResult(
            verdict="WAIT",
            bias=bias,
            reasons=[f"Selected candidate / entry_plan is not READY: {status}"],
        )

    if checklist.get("p0_pass") is not True:
        return RuleResult(
            verdict="WARN",
            bias=bias,
            reasons=[
                "entry status READY but royal_road_procedure_checklist.p0_pass is not true",
                f"missing_or_blocked={checklist.get('p0_missing_or_blocked')}",
            ],
        )

    for key in _REQUIRED_RICH_STEPS:
        st = _step_status(checklist, key)
        if st != "PASS":
            return RuleResult(
                verdict="WARN",
                bias=bias,
                reasons=[f"P0 checklist step {key} is {st}, not PASS."],
            )

    entry = ep.get("entry_price")
    stop = ep.get("stop_price")
    target = ep.get("target_price") or ep.get("target_extended_price")
    rr = ep.get("rr")

    try:
        entry_f = float(entry)
        stop_f = float(stop)
        target_f = float(target)
        rr_f = float(rr)
    except (TypeError, ValueError):
        return RuleResult(
            verdict="UNKNOWN",
            bias=bias,
            reasons=["entry/stop/target/rr cannot be parsed."],
        )

    if rr_f < 2.0:
        return RuleResult(
            verdict="WARN",
            bias=bias,
            reasons=[f"RR too low for normal royal road: {rr_f:.2f} < 2.0"],
        )

    if side == "BUY" and not (stop_f < entry_f < target_f):
        return RuleResult(
            verdict="WARN",
            bias=bias,
            reasons=["Invalid BUY price order: expected stop < entry < target."],
        )

    if side == "SELL" and not (target_f < entry_f < stop_f):
        return RuleResult(
            verdict="WARN",
            bias=bias,
            reasons=["Invalid SELL price order: expected target < entry < stop."],
        )

    return RuleResult(
        verdict="PASS",
        bias=bias,
        reasons=["Rich royal-road payload is READY with P0 checklist PASS."],
    )


__all__ = [
    "evaluate",
    "evaluate_monitor_case",
    "RuleResult",
    "Verdict",
    "Bias",
]
