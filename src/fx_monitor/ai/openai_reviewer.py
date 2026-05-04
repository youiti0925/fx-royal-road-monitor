"""OpenAI-backed reviewer using the Responses API + structured outputs.

Every failure mode (disabled, missing key, SDK absent, API error, malformed
response, schema violation) downgrades cleanly to a safe UNKNOWN ReviewResult
so the deterministic notifier never sees a half-broken result.
"""

from __future__ import annotations

import json
import os
from typing import Any  # noqa: F401

import base64

from ..core.models import ChartPayload, MonitorCase, ReviewResult
from ..knowledge.loader import KnowledgePack
from .prompt_builder import build_prompt
from .schema import parse_review, schema_as_dict
from .visual_prompt_builder import build_visual_review_prompt
from .visual_review_schema import (
    VisualReview,
    parse_visual_review,
    visual_review_schema_as_dict,
)


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


    def visual_review(
        self,
        *,
        image_bytes: bytes,
        context_summary: str = "",
    ) -> VisualReview:
        """Grade the decision-screen image for screen quality only.

        Never used for READY decisions, notifications, trading, or
        order execution. Returns a UNKNOWN VisualReview on every
        failure mode (disabled / missing key / SDK absent / API error
        / malformed response).
        """
        if os.getenv("OPENAI_ENABLED", "false").lower() not in ("1", "true", "yes"):
            return _visual_unknown("openai_disabled")
        api_key = self._explicit_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            return _visual_unknown("openai_api_key_missing")
        if not image_bytes:
            return _visual_unknown("openai_visual_image_missing")

        try:
            from openai import OpenAI
        except Exception as exc:
            return _visual_unknown(f"openai_sdk_import_failed:{type(exc).__name__}")

        prompt = build_visual_review_prompt(context_summary=context_summary)
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:image/png;base64,{b64}"

        try:
            client = OpenAI(api_key=api_key)
            response = client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": prompt.system},
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt.user},
                            {"type": "input_image", "image_url": data_url},
                        ],
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "ai_visual_review",
                        "strict": False,
                        "schema": visual_review_schema_as_dict(),
                    }
                },
                temperature=0,
            )
            text = getattr(response, "output_text", None)
            if not text:
                return _visual_unknown("openai_visual_empty_output")
        except json.JSONDecodeError as exc:
            return _visual_unknown(f"openai_visual_response_not_json:{exc.__class__.__name__}")
        except Exception as exc:
            return _visual_unknown(f"openai_visual_review_failed:{type(exc).__name__}")

        return parse_visual_review("openai", text)


def _visual_unknown(reason: str) -> VisualReview:
    return parse_visual_review(
        "openai",
        {
            "schema_version": "visual_review_v1",
            "verdict": "UNKNOWN",
            "readability": "UNKNOWN",
            "language": "UNKNOWN",
            "royal_road_clarity": "UNKNOWN",
            "line_visibility": "UNKNOWN",
            "safety_clarity": "UNKNOWN",
            "problems": [reason],
            "required_fixes": [],
            "summary_ja": "OpenAIによる画面レビューは行えませんでした。",
        },
    )


__all__ = ["OpenAIReviewer"]
