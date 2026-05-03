"""OpenAI-backed reviewer.

Stub: real API call is not implemented in the scaffold. The interface is
fixed though, so wiring this up later only changes the body of `review()`.
"""

from __future__ import annotations

import os

from ..core.models import ChartPayload, ReviewResult
from ..knowledge.loader import KnowledgePack
from .prompt_builder import build_prompt
from .schema import parse_review


class OpenAIReviewer:
    provider = "openai"

    def __init__(
        self,
        pack: KnowledgePack,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.pack = pack
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def review(self, payload: ChartPayload, image_bytes: bytes | None = None) -> ReviewResult:
        if not self.api_key:
            return ReviewResult(
                provider=self.provider,
                verdict="UNKNOWN",
                bias="none",
                reasons=["OPENAI_API_KEY not set; reviewer disabled."],
            )
        # Build prompt now so a real implementation can plug it in directly.
        _prompt = build_prompt(payload, self.pack)
        # TODO: call OpenAI Responses / Chat Completions with image + JSON schema.
        # For now, return UNKNOWN so the pipeline stays safe.
        return parse_review(
            self.provider,
            {
                "verdict": "UNKNOWN",
                "bias": "none",
                "confidence": 0.0,
                "reasons": ["OpenAI reviewer not yet implemented in scaffold."],
            },
        )


__all__ = ["OpenAIReviewer"]
