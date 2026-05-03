"""Domain models shared across rule engine, AI reviewers, and notifier."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

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


class CompareOutcome(BaseModel):
    result: CompareResult
    bias: Bias = "none"
    notes: list[str] = Field(default_factory=list)


class NotificationDecision(BaseModel):
    level: NotifyLevel
    reason: str
    title: str = ""
    body: str = ""
