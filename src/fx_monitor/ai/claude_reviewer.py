"""Anthropic Claude-backed reviewer.

Stub mirroring OpenAIReviewer. Real API call left to a follow-up PR.
"""

from __future__ import annotations

import os

from ..core.models import ChartPayload, ReviewResult
from ..knowledge.loader import KnowledgePack
from .prompt_builder import build_prompt
from .schema import parse_review


class ClaudeReviewer:
    provider = "claude"

    def __init__(
        self,
        pack: KnowledgePack,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.pack = pack
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def review(self, payload: ChartPayload, image_bytes: bytes | None = None) -> ReviewResult:
        if not self.api_key:
            return ReviewResult(
                provider=self.provider,
                verdict="UNKNOWN",
                bias="none",
                reasons=["ANTHROPIC_API_KEY not set; reviewer disabled."],
            )
        _prompt = build_prompt(payload, self.pack)
        # TODO: call Anthropic Messages API with image + JSON schema.
        return parse_review(
            self.provider,
            {
                "verdict": "UNKNOWN",
                "bias": "none",
                "confidence": 0.0,
                "reasons": ["Claude reviewer not yet implemented in scaffold."],
            },
        )


__all__ = ["ClaudeReviewer"]
