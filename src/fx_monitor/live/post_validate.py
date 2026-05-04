"""Layer 3: post-validation of AI-authored decision specs.

The AI judge can hallucinate. Layer 3's job is to catch hallucinations
that contradict the numeric facts the AI was given. Concretely we check:

- Coordinate sanity: lines and points are inside (or near) the recent
  price range.
- Anchor touch: a line that claims an anchor candle should actually pass
  near that candle's body.
- Safety flags: defence in depth against any flag flip the schema layer
  somehow let through.

Anything classified as ``error`` causes the caller to downgrade
``final_status`` to ``UNKNOWN``. ``warning`` is recorded but does not
downgrade — it's there to surface "looks fishy" cases on the dashboard.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from fx_monitor.ai.decision_screen_spec_schema import AiDecisionScreenSpec

from .market_pack_v2 import MarketAnalysisPackV2

Severity = Literal["error", "warning"]


class ValidationIssue(BaseModel):
    code: str
    severity: Severity
    detail: str = ""


class PostValidationResult(BaseModel):
    schema_version: Literal["post_validation_v1"] = "post_validation_v1"
    ok: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    downgraded: bool = False

    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]


def _price_range(pack: MarketAnalysisPackV2) -> tuple[float, float]:
    if not pack.candles:
        return (pack.current_price, pack.current_price)
    lo = min(c.l for c in pack.candles)
    hi = max(c.h for c in pack.candles)
    return (lo, hi)


def post_validate(
    spec: AiDecisionScreenSpec,
    pack: MarketAnalysisPackV2,
    *,
    out_of_range_tolerance: float = 0.01,
    anchor_touch_atr_ratio: float = 0.5,
) -> PostValidationResult:
    """Validate an AI-authored spec against the numeric facts it was given.

    ``out_of_range_tolerance`` allows e.g. a target line slightly outside
    the recent 60-bar range to remain a warning rather than an error
    (extension lines beyond the last bar are common and legitimate).
    """
    issues: list[ValidationIssue] = []

    pmin, pmax = _price_range(pack)
    span = pmax - pmin if pmax > pmin else max(pack.atr.m5_14, 1e-9)
    lo_bound = pmin - span * out_of_range_tolerance
    hi_bound = pmax + span * out_of_range_tolerance

    # ---- Line coordinate checks ----
    for line in spec.lines:
        if line.price is not None:
            if not (lo_bound <= line.price <= hi_bound):
                issues.append(
                    ValidationIssue(
                        code="line_out_of_range",
                        severity="error",
                        detail=f"line={line.id} price={line.price}",
                    )
                )
        if line.start_price is not None and not (lo_bound <= line.start_price <= hi_bound):
            issues.append(
                ValidationIssue(
                    code="line_start_out_of_range",
                    severity="warning",
                    detail=f"line={line.id} start_price={line.start_price}",
                )
            )
        if line.end_price is not None and not (lo_bound <= line.end_price <= hi_bound):
            issues.append(
                ValidationIssue(
                    code="line_end_out_of_range",
                    severity="warning",
                    detail=f"line={line.id} end_price={line.end_price}",
                )
            )

    # ---- Point coordinate checks ----
    for point in spec.points:
        if point.price is None:
            continue
        if not (lo_bound <= point.price <= hi_bound):
            issues.append(
                ValidationIssue(
                    code="point_out_of_range",
                    severity="error",
                    detail=f"point={point.id} price={point.price}",
                )
            )
        if point.index is not None and not (0 <= point.index < len(pack.candles)):
            issues.append(
                ValidationIssue(
                    code="point_index_oob",
                    severity="error",
                    detail=f"point={point.id} index={point.index}",
                )
            )

    # ---- Anchor touch check ----
    point_by_id = {p.id: p for p in spec.points}
    atr = pack.atr.m5_14 if pack.atr.m5_14 > 0 else 1e-9
    for line in spec.lines:
        if not line.anchor_points or line.price is None:
            continue
        for anchor_id in line.anchor_points:
            anchor = point_by_id.get(anchor_id)
            if anchor is None or anchor.index is None:
                continue
            if not (0 <= anchor.index < len(pack.candles)):
                continue
            candle = pack.candles[anchor.index]
            slack = atr * anchor_touch_atr_ratio
            if not (candle.l - slack <= line.price <= candle.h + slack):
                issues.append(
                    ValidationIssue(
                        code="line_not_touching_anchor",
                        severity="warning",
                        detail=f"line={line.id} anchor={anchor.id}",
                    )
                )

    # ---- Safety flag defence in depth ----
    if not spec.observation_only:
        issues.append(
            ValidationIssue(
                code="observation_only_flipped",
                severity="error",
                detail="spec.observation_only must remain True",
            )
        )
    if spec.used_for_ready or spec.used_for_notification or spec.used_for_trading:
        issues.append(
            ValidationIssue(
                code="safety_flag_flipped",
                severity="error",
                detail=(
                    f"used_for_ready={spec.used_for_ready} "
                    f"used_for_notification={spec.used_for_notification} "
                    f"used_for_trading={spec.used_for_trading}"
                ),
            )
        )

    has_error = any(i.severity == "error" for i in issues)
    return PostValidationResult(
        ok=not has_error,
        issues=issues,
        downgraded=has_error,
    )


__all__ = [
    "PostValidationResult",
    "ValidationIssue",
    "Severity",
    "post_validate",
]
