"""JSON schema for the AI reviewer output.

This is the *single source of truth* for the contract between the AI and us.
prompt_builder.py embeds this schema into the prompt; the reviewers validate
the response against it before turning it into a ReviewResult.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ..core.models import ReviewResult

REVIEW_OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ReviewResult",
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "bias", "confidence", "reasons"],
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["PASS", "WAIT", "WARN", "BLOCK", "UNKNOWN"],
        },
        "bias": {"type": "string", "enum": ["long", "short", "none"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "disagreements": {"type": "array", "items": {"type": "string"}},
        "missing": {"type": "array", "items": {"type": "string"}},
        "suggested_invalidation": {"type": ["number", "null"]},
        "suggested_target": {"type": ["number", "null"]},
    },
}


def schema_as_json(indent: int = 2) -> str:
    """Return the JSON schema as a string ready to embed in a prompt."""
    return json.dumps(REVIEW_OUTPUT_SCHEMA, indent=indent, ensure_ascii=False)


def parse_review(provider: str, payload: str | dict[str, Any]) -> ReviewResult:
    """Parse AI response (str of JSON or dict) into a ReviewResult.

    On any failure (bad JSON, schema violation, value out of range) returns a
    safe UNKNOWN result so the upstream pipeline never crashes on a misbehaving
    model.
    """
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            return ReviewResult(
                provider=provider,
                verdict="UNKNOWN",
                bias="none",
                confidence=0.0,
                reasons=[f"Invalid JSON from {provider}: {e}"],
            )
    else:
        data = payload

    try:
        return ReviewResult(provider=provider, **data)
    except ValidationError as e:
        return ReviewResult(
            provider=provider,
            verdict="UNKNOWN",
            bias="none",
            confidence=0.0,
            reasons=[f"Schema violation from {provider}: {e.errors(include_url=False)[:3]}"],
        )


__all__ = ["REVIEW_OUTPUT_SCHEMA", "schema_as_json", "parse_review"]
