"""Mock reviewer + canned review payload helpers.

Used by tests and CI dry-runs so the whole pipeline can be exercised without
calling external APIs. The mock outputs follow the same JSON schema as a
real reviewer and pass through `parse_review()`, which means they also
exercise our P0 invariant checks.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..core.models import ChartPayload, MonitorCase, ReviewResult
from ..core.rule_engine import evaluate
from .schema import REQUIRED_STEP_KEYS, parse_review


def _step(key: str, status: str, reason_ja: str = "") -> dict[str, Any]:
    return {
        "key": key,
        "status": status,
        "reason_ja": reason_ja or f"[mock] {key}={status}",
        "evidence": {},
        "missing": [],
        "cautions": [],
    }


def _full_steps(status: str) -> list[dict[str, Any]]:
    return [_step(k, status) for k in REQUIRED_STEP_KEYS]


def _base_review(verdict: str, bias: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "bias": bias,
        "confidence": 0.6,
        "reasons": [f"[mock] verdict={verdict}"],
        "disagreements": [],
        "missing": [],
        "suggested_invalidation": None,
        "suggested_target": None,
        "steps": steps,
        "line_review": {
            "neckline_valid": verdict == "PASS",
            "numeric_trendline_valid": verdict == "PASS",
            "structural_line_valid": verdict == "PASS",
            "numeric_structural_alignment": "MATCH" if verdict == "PASS" else "UNKNOWN",
            "problems": [],
        },
        "wave_review": {
            "pattern_valid": verdict == "PASS",
            "pattern_type": "DT" if bias == "short" else ("DB" if bias == "long" else ""),
            "wave_points_valid": verdict == "PASS",
            "problems": [],
        },
        "entry_review": {
            "entry_natural": verdict == "PASS",
            "entry_timing": "GOOD" if verdict == "PASS" else "UNKNOWN",
            "reason_ja": f"[mock] {verdict}",
            "problems": [],
        },
        "risk_review": {
            "stop_structural": verdict == "PASS",
            "target_realistic": verdict == "PASS",
            "rr_ok": verdict == "PASS",
            "problems": [],
        },
        "disagreement_with_system": {
            "has_disagreement": False,
            "severity": "NONE",
            "reason_ja": "",
        },
    }


def mock_ready_review(bias: str = "long") -> dict[str, Any]:
    """A complete, schema-valid PASS review (all P0 steps PASS)."""
    return _base_review("PASS", bias, _full_steps("PASS"))


def mock_wait_retest_review(bias: str = "long") -> dict[str, Any]:
    """Pre-trigger setup: breakout PASS, retest WAIT."""
    steps = _full_steps("PASS")
    for s in steps:
        if s["key"] == "retest":
            s["status"] = "WAIT"
            s["reason_ja"] = "[mock] WNL broke but retest not confirmed"
        if s["key"] == "confirmation_candle":
            s["status"] = "WAIT"
        if s["key"] == "entry":
            s["status"] = "WAIT"
    review = _base_review("WAIT", bias, steps)
    review["reasons"] = ["[mock] WAIT_RETEST"]
    return review


def mock_unknown_review(bias: str = "none") -> dict[str, Any]:
    """Insufficient evidence: every step UNKNOWN."""
    review = _base_review("UNKNOWN", bias, _full_steps("UNKNOWN"))
    review["reasons"] = ["[mock] insufficient evidence"]
    review["missing"] = ["chart_image", "htf_payload"]
    return review


class MockReviewer:
    """Reviewer that mirrors the rule engine into the new schema.

    - rule PASS -> ready review (all P0 PASS)
    - rule WAIT -> wait_retest review
    - everything else -> unknown review
    """

    def __init__(self, provider: str = "mock", confidence: float = 0.6) -> None:
        self.provider = provider
        self.confidence = confidence

    def review(
        self,
        payload: ChartPayload | MonitorCase,
        image_bytes: bytes | None = None,
    ) -> ReviewResult:
        # MonitorCase: mirror the legacy rule engine off ``chart_payload`` so
        # the mock works unchanged in fixture / draft / demo paths.
        chart_payload = payload.chart_payload if isinstance(payload, MonitorCase) else payload
        rule = evaluate(chart_payload)
        if rule.verdict == "PASS":
            data = mock_ready_review(bias=rule.bias)
        elif rule.verdict == "WAIT":
            data = mock_wait_retest_review(bias=rule.bias if rule.bias != "none" else "long")
        else:
            data = mock_unknown_review()

        data = deepcopy(data)
        data["confidence"] = self.confidence
        data["reasons"] = [f"[mock {self.provider}] mirrors rule engine ({rule.verdict})"] + [
            f"  - {r}" for r in rule.reasons
        ]
        return parse_review(self.provider, data)


__all__ = [
    "MockReviewer",
    "mock_ready_review",
    "mock_wait_retest_review",
    "mock_unknown_review",
]
