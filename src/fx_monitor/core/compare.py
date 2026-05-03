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
        if openai.bias != claude.bias or openai.bias == "none":
            return CompareOutcome(
                result="DISAGREE",
                notes=[f"Both PASS but bias differs: openai={openai.bias}, claude={claude.bias}."],
            )
        # Even when both are PASS with matching bias, any explicit disagreement
        # raised by either reviewer downgrades the comparison to DISAGREE so
        # that READY is never emitted on a flagged setup.
        if openai.disagreements or claude.disagreements:
            return CompareOutcome(
                result="DISAGREE",
                notes=[
                    "Both PASS but at least one reviewer raised disagreements; "
                    "refusing AGREE_PASS for safety."
                ],
            )
        # Same goes for an explicit disagreement_with_system block.
        for r in (openai, claude):
            d = r.disagreement_with_system
            if d is not None and d.has_disagreement:
                return CompareOutcome(
                    result="DISAGREE",
                    notes=[
                        f"{r.provider} flagged disagreement_with_system "
                        f"(severity={d.severity}); refusing AGREE_PASS."
                    ],
                )
        return CompareOutcome(
            result="AGREE_PASS",
            bias=openai.bias,
            notes=["Both reviewers PASS with matching bias and no disagreements."],
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
