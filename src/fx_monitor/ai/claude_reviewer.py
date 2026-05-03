"""Anthropic Claude reviewer using the Messages API + tool input_schema.

The model is forced to call a single tool whose input_schema is exactly our
review JSON schema. As with OpenAIReviewer, every failure mode falls through
to a safe UNKNOWN ReviewResult.
"""

from __future__ import annotations

import os
from typing import Any

from ..core.models import ChartPayload, MonitorCase, ReviewResult
from ..knowledge.loader import KnowledgePack
from .prompt_builder import build_prompt
from .schema import parse_review, schema_as_dict

_TOOL_NAME = "submit_ai_royal_road_review"


def _unknown(reason: str) -> ReviewResult:
    return parse_review(
        "claude",
        {
            "verdict": "UNKNOWN",
            "bias": "none",
            "confidence": 0.0,
            "reasons": [reason],
            "disagreements": [],
            "missing": [reason],
            "steps": [],
        },
    )


class ClaudeReviewer:
    provider = "claude"

    def __init__(
        self,
        pack: KnowledgePack | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.pack = pack
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self._explicit_api_key = api_key

    def review(
        self,
        payload: ChartPayload | MonitorCase | dict[str, Any],
        image_bytes: bytes | None = None,
    ) -> ReviewResult:
        if os.getenv("ANTHROPIC_ENABLED", "false").lower() not in ("1", "true", "yes"):
            return _unknown("anthropic_disabled")

        api_key = self._explicit_api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return _unknown("anthropic_api_key_missing")

        try:
            import anthropic
        except Exception as exc:
            return _unknown(f"anthropic_sdk_import_failed:{type(exc).__name__}")

        prompt = build_prompt(payload, self.pack)
        schema = schema_as_dict()

        try:
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0,
                system=prompt.system,
                messages=[{"role": "user", "content": prompt.user}],
                tools=[
                    {
                        "name": _TOOL_NAME,
                        "description": (
                            "Submit the FX royal-road review as strict structured JSON. "
                            "Use this tool exactly once."
                        ),
                        "input_schema": schema,
                    }
                ],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
            )
        except Exception as exc:
            return _unknown(f"anthropic_review_failed:{type(exc).__name__}")

        for block in getattr(msg, "content", None) or []:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", "") == _TOOL_NAME:
                data = getattr(block, "input", None)
                if isinstance(data, dict):
                    return parse_review("claude", data)
                return _unknown("anthropic_tool_input_not_dict")

        return _unknown("anthropic_tool_use_missing")


__all__ = ["ClaudeReviewer"]
