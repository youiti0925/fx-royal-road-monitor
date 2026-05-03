"""OpenAI-backed reviewer using the Responses API + structured outputs.

Every failure mode (disabled, missing key, SDK absent, API error, malformed
response, schema violation) downgrades cleanly to a safe UNKNOWN ReviewResult
so the deterministic notifier never sees a half-broken result.
"""

from __future__ import annotations

import json
import os
from typing import Any

from ..core.models import ChartPayload, MonitorCase, ReviewResult
from ..knowledge.loader import KnowledgePack
from .prompt_builder import build_prompt
from .schema import parse_review, schema_as_dict


def _unknown(reason: str) -> ReviewResult:
    return parse_review(
        "openai",
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


class OpenAIReviewer:
    provider = "openai"

    def __init__(
        self,
        pack: KnowledgePack | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.pack = pack
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._explicit_api_key = api_key

    def review(
        self,
        payload: ChartPayload | MonitorCase | dict[str, Any],
        image_bytes: bytes | None = None,
    ) -> ReviewResult:
        if os.getenv("OPENAI_ENABLED", "false").lower() not in ("1", "true", "yes"):
            return _unknown("openai_disabled")

        api_key = self._explicit_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            return _unknown("openai_api_key_missing")

        try:
            from openai import OpenAI
        except Exception as exc:
            return _unknown(f"openai_sdk_import_failed:{type(exc).__name__}")

        prompt = build_prompt(payload, self.pack)

        try:
            client = OpenAI(api_key=api_key)
            response = client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": prompt.system},
                    {"role": "user", "content": prompt.user},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "ai_royal_road_review",
                        "strict": True,
                        "schema": schema_as_dict(),
                    }
                },
                temperature=0,
            )
            text = getattr(response, "output_text", None)
            if not text:
                return _unknown("openai_empty_output")
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return _unknown(f"openai_response_not_json:{exc.__class__.__name__}")
        except Exception as exc:
            return _unknown(f"openai_review_failed:{type(exc).__name__}")

        return parse_review("openai", data)


__all__ = ["OpenAIReviewer"]
