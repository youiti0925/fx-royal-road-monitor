"""AI-authored decision screen spec.

Hard contract — pinned by tests:

- ``observation_only=True`` (always)
- ``used_for_ready=False`` (always)
- ``used_for_notification=False`` (always)
- ``used_for_trading=False`` (always)

If a model's payload tries to flip any of those four flags, the parser
returns a SAFE-UNKNOWN spec instead. The schema is separate from the
trading-review and visual-review schemas — never touches the
notification / READY path.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

Verdict = Literal["PASS", "WAIT", "WARN", "BLOCK", "UNKNOWN"]
Side = Literal["BUY", "SELL", "NEUTRAL"]
LineKind = Literal[
    "neckline",
    "invalidation",
    "target",
    "trendline",
    "support",
    "resistance",
    "channel",
    "event",
    "other",
]
ZoneKind = Literal[
    "support",
    "resistance",
    "event",
    "fibonacci_prime",
    "buildup",
    "stop_zone_upper",
    "stop_zone_lower",
    "confluence",
    "other",
]
FinalStatus = Literal[
    "SUPPRESSED",
    "HOLD",
    "WAIT_BREAKOUT",
    "WAIT_RETEST",
    "WAIT_TRIGGER",
    "WAIT_EVENT_CLEAR",
    "UNKNOWN",
]


class ScreenPoint(BaseModel):
    id: str
    label: str
    role: str
    index: int | None = None
    timestamp: str | None = None
    price: float | None = None
    reason_ja: str = ""


class ScreenLine(BaseModel):
    id: str
    label: str
    kind: LineKind
    role: str
    price: float | None = None
    start_index: int | None = None
    start_price: float | None = None
    end_index: int | None = None
    end_price: float | None = None
    anchor_points: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    reason_ja: str = ""
    cautions: list[str] = Field(default_factory=list)


class ScreenZone(BaseModel):
    id: str
    label: str
    kind: ZoneKind
    price_low: float | None = None
    price_high: float | None = None
    index_low: int | None = None
    index_high: int | None = None
    reason_ja: str = ""
    confidence: float = 0.0


class ProcedureStepSpec(BaseModel):
    key: str
    label_ja: str
    status: Verdict
    result_ja: str
    missing_or_waiting: list[str] = Field(default_factory=list)


class AiDecisionScreenSpec(BaseModel):
    schema_version: str = "ai_decision_screen_spec_v1"
    provider: Literal["openai", "claude"]
    observation_only: bool = True
    used_for_ready: bool = False
    used_for_notification: bool = False
    used_for_trading: bool = False

    symbol: str
    timeframe: str
    title_ja: str = "MVP-1 王道判定プレビュー"
    side: Side = "NEUTRAL"
    final_status: FinalStatus = "SUPPRESSED"

    pattern_label_ja: str = ""
    market_story_ja: str = ""

    points: list[ScreenPoint] = Field(default_factory=list)
    lines: list[ScreenLine] = Field(default_factory=list)
    zones: list[ScreenZone] = Field(default_factory=list)
    procedure_steps: list[ProcedureStepSpec] = Field(default_factory=list)

    entry_candidate_ja: str = "本番ENTRY候補ではありません"
    stop_candidate_ja: str = "本番STOP候補ではありません"
    target_candidate_ja: str = "本番TP候補ではありません"
    rr_comment_ja: str = "MVP-1ではREADY判定に未使用"

    problems: list[str] = Field(default_factory=list)
    required_fixes: list[str] = Field(default_factory=list)
    summary_ja: str = ""


def decision_screen_spec_schema_as_dict() -> dict[str, Any]:
    return AiDecisionScreenSpec.model_json_schema()


def decision_screen_spec_schema_as_json(indent: int = 2) -> str:
    return json.dumps(
        decision_screen_spec_schema_as_dict(), indent=indent, ensure_ascii=False
    )


def safe_unknown_spec(
    *,
    provider: str,
    symbol: str,
    timeframe: str,
    reason: str,
) -> AiDecisionScreenSpec:
    return AiDecisionScreenSpec(
        provider=provider,  # type: ignore[arg-type]
        symbol=symbol,
        timeframe=timeframe,
        side="NEUTRAL",
        final_status="UNKNOWN",
        problems=[reason],
        summary_ja=f"{provider}は王道判定画面を生成できませんでした ({reason})。",
    )


def parse_decision_screen_spec(
    *,
    provider: str,
    payload: str | dict[str, Any],
    symbol: str,
    timeframe: str,
) -> AiDecisionScreenSpec:
    """Parse a model response into an AiDecisionScreenSpec.

    Bad JSON / schema violation / missing fields / **anyone trying to
    flip the four hard-contract safety flags** all funnel through to a
    SAFE-UNKNOWN spec — never raises.
    """
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as e:
            return safe_unknown_spec(
                provider=provider,
                symbol=symbol,
                timeframe=timeframe,
                reason=f"invalid JSON: {e}",
            )
    elif isinstance(payload, dict):
        data = dict(payload)
    else:
        return safe_unknown_spec(
            provider=provider,
            symbol=symbol,
            timeframe=timeframe,
            reason=f"unexpected payload type {type(payload).__name__}",
        )

    # Belt-and-suspenders: regardless of what the model returned, the
    # four hard-contract flags must be the safe values. If the model
    # tried to flip any of them, treat the whole spec as UNKNOWN.
    flipped: list[str] = []
    if data.get("observation_only") is False:
        flipped.append("observation_only=false")
    for k in ("used_for_ready", "used_for_notification", "used_for_trading"):
        if data.get(k) is True:
            flipped.append(f"{k}=true")
    if flipped:
        return safe_unknown_spec(
            provider=provider,
            symbol=symbol,
            timeframe=timeframe,
            reason="safety contract violated: " + ", ".join(flipped),
        )

    # Force-set the safe values even if the payload was silent.
    data["observation_only"] = True
    data["used_for_ready"] = False
    data["used_for_notification"] = False
    data["used_for_trading"] = False
    data["provider"] = provider
    data.setdefault("symbol", symbol)
    data.setdefault("timeframe", timeframe)

    try:
        return AiDecisionScreenSpec(**data)
    except ValidationError as e:
        return safe_unknown_spec(
            provider=provider,
            symbol=symbol,
            timeframe=timeframe,
            reason=f"schema violation: {e.errors(include_url=False)[:2]}",
        )


__all__ = [
    "AiDecisionScreenSpec",
    "ScreenPoint",
    "ScreenLine",
    "ScreenZone",
    "ProcedureStepSpec",
    "Verdict",
    "Side",
    "LineKind",
    "FinalStatus",
    "decision_screen_spec_schema_as_dict",
    "decision_screen_spec_schema_as_json",
    "parse_decision_screen_spec",
    "safe_unknown_spec",
    "validate_decision_screen_spec_for_user_preview",
]


def validate_decision_screen_spec_for_user_preview(
    spec: dict | AiDecisionScreenSpec,
    provider: str,
) -> list[str]:
    """Return a list of validation errors that disqualify a spec from
    being shown as a user-facing AI-authored decision screen.

    A populated spec for a user preview must:
    - have ``final_status`` other than UNKNOWN
    - have at least one ``points`` entry
    - have at least one ``lines`` entry
    - have at least one ``procedure_steps`` entry
    - keep the four hard-contract safety flags exactly safe
    """
    if isinstance(spec, AiDecisionScreenSpec):
        data = spec.model_dump(mode="json")
    elif isinstance(spec, dict):
        data = spec
    else:
        return [f"{provider}_spec_not_dict"]

    errors: list[str] = []
    if (data.get("final_status") or "UNKNOWN") == "UNKNOWN":
        errors.append(f"{provider}_final_status_unknown")
    if not data.get("points"):
        errors.append(f"{provider}_points_empty")
    if not data.get("lines"):
        errors.append(f"{provider}_lines_empty")
    if not data.get("procedure_steps"):
        errors.append(f"{provider}_procedure_steps_empty")
    if data.get("observation_only") is not True:
        errors.append(f"{provider}_observation_only_not_true")
    if data.get("used_for_ready") is not False:
        errors.append(f"{provider}_used_for_ready_not_false")
    if data.get("used_for_notification") is not False:
        errors.append(f"{provider}_used_for_notification_not_false")
    if data.get("used_for_trading") is not False:
        errors.append(f"{provider}_used_for_trading_not_false")
    return errors
