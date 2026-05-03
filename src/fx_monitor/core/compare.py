"""Compare two AI reviewer outputs into a single CompareOutcome."""

from __future__ import annotations

from .models import CompareOutcome, ReviewResult


def compare(openai: ReviewResult | None, claude: ReviewResult | None) -> CompareOutcome:
    """Apply the rules in knowledge pack §5.

    - AGREE_PASS   : both PASS and bias matches.
    - AGREE_HOLD   : both reach the same non-PASS verdict.
    - DISAGREE     : verdicts differ, or both PASS but bias differs.
    - INSUFFICIENT : either reviewer is missing or returned UNKNOWN.
    """

    if openai is None or claude is None:
        return CompareOutcome(
            result="INSUFFICIENT",
            notes=["One or both reviewers were not run."],
        )

    if openai.verdict == "UNKNOWN" or claude.verdict == "UNKNOWN":
        return CompareOutcome(
            result="INSUFFICIENT",
            notes=["At least one reviewer returned UNKNOWN."],
        )

    if openai.verdict == "PASS" and claude.verdict == "PASS":
        if openai.bias == claude.bias and openai.bias != "none":
            return CompareOutcome(
                result="AGREE_PASS",
                bias=openai.bias,
                notes=["Both reviewers PASS with matching bias."],
            )
        return CompareOutcome(
            result="DISAGREE",
            notes=[f"Both PASS but bias differs: openai={openai.bias}, claude={claude.bias}."],
        )

    if openai.verdict == claude.verdict:
        return CompareOutcome(
            result="AGREE_HOLD",
            notes=[f"Both reviewers agree on {openai.verdict}."],
        )

    return CompareOutcome(
        result="DISAGREE",
        notes=[f"Verdicts differ: openai={openai.verdict}, claude={claude.verdict}."],
    )


__all__ = ["compare", "CompareOutcome"]
