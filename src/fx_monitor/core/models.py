"""Domain models shared across rule engine, AI reviewers, and notifier."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Verdict = Literal["PASS", "WAIT", "WARN", "BLOCK", "UNKNOWN"]
Bias = Literal["long", "short", "none"]
HtfTrend = Literal["up", "down", "range"]
LtfStructure = Literal["HH-HL", "LH-LL", "range", "broken"]
TriggerType = Literal["breakout", "retest", "pinbar", "engulf", "none"]
CompareResult = Literal["AGREE_PASS", "AGREE_HOLD", "DISAGREE", "INSUFFICIENT"]
NotifyLevel = Literal["READY", "WATCH", "INFO", "SUPPRESSED"]


class HtfContext(BaseModel):
    h4_trend: HtfTrend
    d1_trend: HtfTrend
    key_levels: list[float] = Field(default_factory=list)


class LtfContext(BaseModel):
    structure: LtfStructure
    last_swing_high: float
    last_swing_low: float
    atr_14: float


class TriggerInfo(BaseModel):
    type: TriggerType
    occurred: bool


class CalendarInfo(BaseModel):
    high_impact_within_15min: bool = False


class ChartPayload(BaseModel):
    """Structured payload that we feed to AI reviewers (and the rule engine)."""

    symbol: str
    timeframe: str
    timestamp_utc: datetime
    htf: HtfContext
    ltf: LtfContext
    trigger: TriggerInfo
    calendar: CalendarInfo = Field(default_factory=CalendarInfo)


class RuleResult(BaseModel):
    verdict: Verdict
    bias: Bias
    reasons: list[str] = Field(default_factory=list)


StepStatusValue = Literal["PASS", "WAIT", "WARN", "BLOCK", "UNKNOWN"]
AlignmentValue = Literal["MATCH", "NEAR", "CONFLICT", "NONE", "UNKNOWN"]
EntryTimingValue = Literal["GOOD", "EARLY", "LATE", "UNKNOWN"]
SeverityValue = Literal["NONE", "LOW", "MEDIUM", "HIGH"]


class StepStatus(BaseModel):
    key: str
    status: StepStatusValue
    reason_ja: str = ""
    evidence: dict = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class LineReview(BaseModel):
    neckline_valid: bool = False
    numeric_trendline_valid: bool = False
    structural_line_valid: bool = False
    numeric_structural_alignment: AlignmentValue = "UNKNOWN"
    problems: list[str] = Field(default_factory=list)


class WaveReview(BaseModel):
    pattern_valid: bool = False
    pattern_type: str = ""
    wave_points_valid: bool = False
    problems: list[str] = Field(default_factory=list)


class EntryReview(BaseModel):
    entry_natural: bool = False
    entry_timing: EntryTimingValue = "UNKNOWN"
    reason_ja: str = ""
    problems: list[str] = Field(default_factory=list)


class RiskReview(BaseModel):
    stop_structural: bool = False
    target_realistic: bool = False
    rr_ok: bool = False
    problems: list[str] = Field(default_factory=list)


class DisagreementWithSystem(BaseModel):
    has_disagreement: bool = False
    severity: SeverityValue = "NONE"
    reason_ja: str = ""


class ReviewResult(BaseModel):
    """One AI reviewer's output. Schema is enforced; see ai/schema.py."""

    provider: str
    verdict: Verdict
    bias: Bias
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    reasons: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    suggested_invalidation: float | None = None
    suggested_target: float | None = None
    steps: list[StepStatus] = Field(default_factory=list)
    line_review: LineReview | None = None
    wave_review: WaveReview | None = None
    entry_review: EntryReview | None = None
    risk_review: RiskReview | None = None
    disagreement_with_system: DisagreementWithSystem | None = None


class CompareOutcome(BaseModel):
    result: CompareResult
    bias: Bias = "none"
    notes: list[str] = Field(default_factory=list)


class NotificationDecision(BaseModel):
    level: NotifyLevel
    reason: str
    title: str = ""
    body: str = ""


class MonitorCase(BaseModel):
    """One complete monitoring case.

    chart_payload:
      Minimal deterministic payload used by the legacy/simple rule engine.

    ai_payload:
      Rich royal-road payload sent to OpenAI / Claude.
      This must include entry_plan, structural_lines, checklist, etc.

    source_payload:
      Raw input from existing royal-road system, kept for debugging.
    """

    chart_payload: ChartPayload
    ai_payload: dict[str, Any] = Field(default_factory=dict)
    source_payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "unknown"
    chart_image_path: str | None = None
