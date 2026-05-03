"""Mock reviewer for tests / CI dry-run.

Deterministically maps the rule engine's verdict to a fake AI response.
Useful so we can exercise the whole pipeline without touching external APIs.
"""

from __future__ import annotations

from ..core.models import ChartPayload, ReviewResult
from ..core.rule_engine import evaluate


class MockReviewer:
    def __init__(self, provider: str = "mock", confidence: float = 0.5) -> None:
        self.provider = provider
        self.confidence = confidence

    def review(self, payload: ChartPayload, image_bytes: bytes | None = None) -> ReviewResult:
        rule = evaluate(payload)
        return ReviewResult(
            provider=self.provider,
            verdict=rule.verdict,
            bias=rule.bias,
            confidence=self.confidence,
            reasons=[f"[mock] mirrors rule engine: {r}" for r in rule.reasons],
        )


__all__ = ["MockReviewer"]
