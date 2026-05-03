"""JSON schema for the AI reviewer output.

Source of truth for the contract between the AI and us. prompt_builder.py
embeds this schema into every prompt; parse_review() validates the response,
and on any deviation downgrades the result to a safe UNKNOWN. Hallucinated
values are worse than UNKNOWN.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ..core.models import ReviewResult

# The royal-road procedure stages, in order. Every reviewer must return a
# `steps[]` array that covers every one of these keys (knowledge pack §1).
REQUIRED_STEP_KEYS: list[str] = [
    "environment",
    "htf_direction",
    "dow_structure",
    "support_resistance",
    "numeric_trendline",
    "structural_line",
    "wave_pattern",
    "neckline",
    "breakout",
    "retest",
    "confirmation_candle",
    "entry",
    "stop",
    "target",
    "rr",
    "event",
]

# P0 stages that must be PASS before verdict==PASS is allowed
# (knowledge pack §3 + §17).
P0_STEP_KEYS: list[str] = [
    "wave_pattern",
    "neckline",
    "breakout",
    "retest",
    "confirmation_candle",
    "entry",
    "stop",
    "target",
    "rr",
    "event",
]

_STATUS_ENUM = ["PASS", "WAIT", "WARN", "BLOCK", "UNKNOWN"]
_BIAS_ENUM = ["long", "short", "none"]
_ALIGNMENT_ENUM = ["MATCH", "NEAR", "CONFLICT", "NONE", "UNKNOWN"]
_TIMING_ENUM = ["GOOD", "EARLY", "LATE", "UNKNOWN"]
_SEVERITY_ENUM = ["NONE", "LOW", "MEDIUM", "HIGH"]


REVIEW_OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ReviewResult",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "verdict",
        "bias",
        "confidence",
        "reasons",
        "steps",
        "line_review",
        "wave_review",
        "entry_review",
        "risk_review",
        "disagreement_with_system",
    ],
    "properties": {
        "verdict": {"type": "string", "enum": _STATUS_ENUM},
        "bias": {"type": "string", "enum": _BIAS_ENUM},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "disagreements": {"type": "array", "items": {"type": "string"}},
        "missing": {"type": "array", "items": {"type": "string"}},
        "suggested_invalidation": {"type": ["number", "null"]},
        "suggested_target": {"type": ["number", "null"]},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["key", "status", "reason_ja", "evidence", "missing", "cautions"],
                "properties": {
                    "key": {"type": "string", "enum": REQUIRED_STEP_KEYS},
                    "status": {"type": "string", "enum": _STATUS_ENUM},
                    "reason_ja": {"type": "string"},
                    "evidence": {"type": "object"},
                    "missing": {"type": "array", "items": {"type": "string"}},
                    "cautions": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "line_review": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "neckline_valid",
                "numeric_trendline_valid",
                "structural_line_valid",
                "numeric_structural_alignment",
                "problems",
            ],
            "properties": {
                "neckline_valid": {"type": "boolean"},
                "numeric_trendline_valid": {"type": "boolean"},
                "structural_line_valid": {"type": "boolean"},
                "numeric_structural_alignment": {"type": "string", "enum": _ALIGNMENT_ENUM},
                "problems": {"type": "array", "items": {"type": "string"}},
            },
        },
        "wave_review": {
            "type": "object",
            "additionalProperties": False,
            "required": ["pattern_valid", "pattern_type", "wave_points_valid", "problems"],
            "properties": {
                "pattern_valid": {"type": "boolean"},
                "pattern_type": {"type": "string"},
                "wave_points_valid": {"type": "boolean"},
                "problems": {"type": "array", "items": {"type": "string"}},
            },
        },
        "entry_review": {
            "type": "object",
            "additionalProperties": False,
            "required": ["entry_natural", "entry_timing", "reason_ja", "problems"],
            "properties": {
                "entry_natural": {"type": "boolean"},
                "entry_timing": {"type": "string", "enum": _TIMING_ENUM},
                "reason_ja": {"type": "string"},
                "problems": {"type": "array", "items": {"type": "string"}},
            },
        },
        "risk_review": {
            "type": "object",
            "additionalProperties": False,
            "required": ["stop_structural", "target_realistic", "rr_ok", "problems"],
            "properties": {
                "stop_structural": {"type": "boolean"},
                "target_realistic": {"type": "boolean"},
                "rr_ok": {"type": "boolean"},
                "problems": {"type": "array", "items": {"type": "string"}},
            },
        },
        "disagreement_with_system": {
            "type": "object",
            "additionalProperties": False,
            "required": ["has_disagreement", "severity", "reason_ja"],
            "properties": {
                "has_disagreement": {"type": "boolean"},
                "severity": {"type": "string", "enum": _SEVERITY_ENUM},
                "reason_ja": {"type": "string"},
            },
        },
    },
}


def schema_as_json(indent: int = 2) -> str:
    """Return the JSON schema as a string ready to embed in a prompt."""
    return json.dumps(REVIEW_OUTPUT_SCHEMA, indent=indent, ensure_ascii=False)


def _safe_unknown(provider: str, why: str) -> ReviewResult:
    return ReviewResult(
        provider=provider,
        verdict="UNKNOWN",
        bias="none",
        confidence=0.0,
        reasons=[f"[safe-unknown] {why}"],
    )


def _validate_pass_invariants(provider: str, data: dict[str, Any]) -> ReviewResult | None:
    """Enforce knowledge pack §3 / §17 P0 invariants for verdict==PASS.

    Returns a downgraded UNKNOWN ReviewResult if any invariant is violated;
    otherwise returns None and the caller proceeds with the normal parse.
    """
    if data.get("verdict") != "PASS":
        return None

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        return _safe_unknown(provider, "verdict=PASS but steps[] missing or empty")

    by_key: dict[str, dict[str, Any]] = {}
    for s in steps:
        if not isinstance(s, dict):
            return _safe_unknown(provider, "verdict=PASS but a step entry is not an object")
        key = s.get("key")
        if isinstance(key, str):
            by_key[key] = s

    missing_keys = [k for k in REQUIRED_STEP_KEYS if k not in by_key]
    if missing_keys:
        return _safe_unknown(
            provider,
            f"verdict=PASS but required step keys missing: {missing_keys}",
        )

    for k in P0_STEP_KEYS:
        status = by_key[k].get("status")
        if status != "PASS":
            return _safe_unknown(
                provider,
                f"verdict=PASS but P0 step {k!r} is {status!r} (must be PASS)",
            )

    # Belt-and-suspenders: explicit checks the user spec calls out.
    if by_key["confirmation_candle"].get("status") != "PASS":
        return _safe_unknown(provider, "verdict=PASS but confirmation_candle is not PASS")
    if by_key["rr"].get("status") != "PASS":
        return _safe_unknown(provider, "verdict=PASS but rr is not PASS")
    if by_key["event"].get("status") == "BLOCK":
        return _safe_unknown(provider, "verdict=PASS but event is BLOCK")

    return None


def parse_review(provider: str, payload: str | dict[str, Any]) -> ReviewResult:
    """Parse an AI response into a ReviewResult, downgrading to UNKNOWN on any
    schema or invariant violation.
    """
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            return _safe_unknown(provider, f"invalid JSON from {provider}: {e}")
    elif isinstance(payload, dict):
        data = payload
    else:
        return _safe_unknown(provider, f"unexpected payload type {type(payload).__name__}")

    invariant_failure = _validate_pass_invariants(provider, data)
    if invariant_failure is not None:
        return invariant_failure

    try:
        return ReviewResult(provider=provider, **data)
    except ValidationError as e:
        return _safe_unknown(
            provider,
            f"schema violation from {provider}: {e.errors(include_url=False)[:3]}",
        )


__all__ = [
    "REVIEW_OUTPUT_SCHEMA",
    "REQUIRED_STEP_KEYS",
    "P0_STEP_KEYS",
    "schema_as_json",
    "parse_review",
]
