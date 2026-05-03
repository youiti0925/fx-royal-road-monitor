"""Deterministic royal-road rule check.

This is the *non-AI* layer. It must reach a conclusion using only the payload,
without calling out to any model. The AI reviewers are advisory; this engine
plus compare.py + notifier.py form the final decision path.
"""

from __future__ import annotations

from .models import Bias, ChartPayload, RuleResult, Verdict


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


__all__ = ["evaluate", "RuleResult", "Verdict", "Bias"]
