"""Visual review schema — observation-only screen quality grading.

This schema is **separate** from the trading-review schema in
``fx_monitor.ai.schema``. It exists so OpenAI / Claude can grade the
*screen* (decision_screen.png) for clarity / Japanese UI / safety
markings — not for trading.

A VisualReview is never used for:

- READY decisions
- notification dispatch
- trading
- order execution

It is used only to detect whether the preview screen is humanly
readable and clearly labelled as observation-only.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

VisualReviewVerdict = Literal["PASS", "WARN", "FAIL", "UNKNOWN"]
VisualReviewGrade = Literal["GOOD", "OK", "BAD", "UNKNOWN"]
VisualReviewLanguage = Literal["JA", "EN", "MIXED", "UNKNOWN"]


class VisualReview(BaseModel):
    """One AI provider's grade of the decision screen image."""

    schema_version: str = "visual_review_v1"
    provider: str
    verdict: VisualReviewVerdict
    readability: VisualReviewGrade = "UNKNOWN"
    language: VisualReviewLanguage = "UNKNOWN"
    royal_road_clarity: VisualReviewGrade = "UNKNOWN"
    line_visibility: VisualReviewGrade = "UNKNOWN"
    safety_clarity: VisualReviewGrade = "UNKNOWN"
    problems: list[str] = Field(default_factory=list)
    required_fixes: list[str] = Field(default_factory=list)
    summary_ja: str = ""

    # Hard contract: this object is observation-only.
    used_for_ready: bool = False
    used_for_notification: bool = False
    used_for_trading: bool = False


VISUAL_REVIEW_OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "VisualReview",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "verdict",
        "readability",
        "language",
        "royal_road_clarity",
        "line_visibility",
        "safety_clarity",
        "problems",
        "required_fixes",
        "summary_ja",
    ],
    "properties": {
        "schema_version": {"type": "string"},
        "verdict": {"type": "string", "enum": ["PASS", "WARN", "FAIL", "UNKNOWN"]},
        "readability": {"type": "string", "enum": ["GOOD", "OK", "BAD", "UNKNOWN"]},
        "language": {"type": "string", "enum": ["JA", "EN", "MIXED", "UNKNOWN"]},
        "royal_road_clarity": {
            "type": "string",
            "enum": ["GOOD", "OK", "BAD", "UNKNOWN"],
        },
        "line_visibility": {
            "type": "string",
            "enum": ["GOOD", "OK", "BAD", "UNKNOWN"],
        },
        "safety_clarity": {
            "type": "string",
            "enum": ["GOOD", "OK", "BAD", "UNKNOWN"],
        },
        "problems": {"type": "array", "items": {"type": "string"}},
        "required_fixes": {"type": "array", "items": {"type": "string"}},
        "summary_ja": {"type": "string"},
    },
}


def visual_review_schema_as_json(indent: int = 2) -> str:
    return json.dumps(VISUAL_REVIEW_OUTPUT_SCHEMA, indent=indent, ensure_ascii=False)


def visual_review_schema_as_dict() -> dict[str, Any]:
    return json.loads(visual_review_schema_as_json())


def _unknown(provider: str, why: str) -> VisualReview:
    return VisualReview(
        provider=provider,
        verdict="UNKNOWN",
        problems=[f"[safe-unknown] {why}"],
        summary_ja="visual reviewが行えませんでした。",
    )


def parse_visual_review(provider: str, payload: str | dict[str, Any]) -> VisualReview:
    """Parse an AI response into a VisualReview. Bad payload -> UNKNOWN."""
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            return _unknown(provider, f"invalid JSON: {e}")
    elif isinstance(payload, dict):
        data = payload
    else:
        return _unknown(provider, f"unexpected payload type {type(payload).__name__}")

    try:
        return VisualReview(provider=provider, **data)
    except ValidationError as e:
        return _unknown(provider, f"schema violation: {e.errors(include_url=False)[:2]}")


__all__ = [
    "VisualReview",
    "VisualReviewVerdict",
    "VisualReviewGrade",
    "VisualReviewLanguage",
    "VISUAL_REVIEW_OUTPUT_SCHEMA",
    "visual_review_schema_as_json",
    "visual_review_schema_as_dict",
    "parse_visual_review",
]
