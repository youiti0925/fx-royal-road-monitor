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
    image_path: str | None = None

    @property
    def should_dispatch(self) -> bool:
        """True when this decision should be sent to notification backends."""
        return self.level not in ("SUPPRESSED", "INFO")


class MarketCandle(BaseModel):
    """One OHLC candle. Validation is lenient on purpose: an invalid OHLC
    order is recorded as a snapshot warning rather than raised, so a single
    bad row never crashes the monitor."""

    timestamp_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None

    def validate_ohlc_order(self) -> bool:
        return self.high >= max(self.open, self.close) and self.low <= min(
            self.open, self.close
        )


class MarketSnapshot(BaseModel):
    symbol: str
    timeframe: str
    source: str
    candles: list[MarketCandle] = Field(default_factory=list)
    fetched_at_utc: datetime | None = None
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return len(self.candles) == 0

    @property
    def last_close(self) -> float | None:
        if not self.candles:
            return None
        return self.candles[-1].close


PivotKind = Literal["HIGH", "LOW"]


class PivotPoint(BaseModel):
    index: int
    timestamp_utc: datetime
    price: float
    kind: PivotKind
    strength: int = 1


class RoyalRoadDraftPayload(BaseModel):
    """Observation-only draft payload synthesized from raw OHLC.

    This is **not** a trading signal. By construction it must never lead
    to a READY notification — the rule engine's draft guard refuses to
    return PASS for any payload with ``observation_only=True``.
    """

    symbol: str
    timeframe: str
    source: str
    timestamp_utc: datetime | None = None

    pivots: list[PivotPoint] = Field(default_factory=list)
    rough_support_resistance: dict[str, Any] = Field(default_factory=dict)
    rough_wave_context: dict[str, Any] = Field(default_factory=dict)

    entry_plan: dict[str, Any] = Field(default_factory=dict)
    selected_entry_candidate: dict[str, Any] = Field(default_factory=dict)
    royal_road_procedure_checklist: dict[str, Any] = Field(default_factory=dict)

    warnings: list[str] = Field(default_factory=list)
    observation_only: bool = True
    used_in_final_action: bool = False


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
