"""Numeric-fact-only market analysis pack for the live layer.

This pack is what we hand to the AI judge. It contains only
machine-computable measurements: OHLC, multi-scale pivots, ATRs,
recent ranges, calendar events, session label.

No code-derived judgements are present. The AI is responsible for
interpreting the facts; the live pipeline must not pre-decide for it.
The CI safety lint asserts the forbidden keys never appear in this
module's source.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .candle import Candle
from .pivots_v2 import PivotPointV2

SessionLabel = Literal["TOKYO", "LONDON", "NY", "OVERLAP", "QUIET"]


class AtrPack(BaseModel):
    m5_14: float = 0.0
    h1_14: float | None = None
    h4_14: float | None = None


class RangePack(BaseModel):
    high_24h: float
    low_24h: float
    high_1w: float | None = None
    low_1w: float | None = None


class CalendarEvent(BaseModel):
    name: str
    impact: Literal["LOW", "MEDIUM", "HIGH"]
    minutes_until: int  # negative if the event is already past


class MarketAnalysisPackV2(BaseModel):
    """Numeric-fact pack handed to the AI judge.

    The schema deliberately excludes any field that would amount to a
    code-side opinion about the chart (no precomputed pattern label,
    no precomputed neckline, no inferred trendlines). Adding such
    fields would re-introduce the GIGO failure mode where the AI
    inherits a code-side judgement instead of forming its own.
    """

    schema_version: Literal["market_analysis_pack_v2"] = "market_analysis_pack_v2"
    symbol: str
    timeframe: Literal["M5"] = "M5"
    asof_utc: datetime
    candles: list[Candle] = Field(default_factory=list)
    pivots: list[PivotPointV2] = Field(default_factory=list)
    atr: AtrPack = Field(default_factory=AtrPack)
    recent_range: RangePack
    calendar_events_within_60min: list[CalendarEvent] = Field(default_factory=list)
    current_price: float
    current_spread: float | None = None
    session: SessionLabel = "QUIET"


def _classify_session(asof_utc: datetime) -> SessionLabel:
    """Coarse FX session label by UTC hour.

    Tokyo:   00:00 - 08:00 UTC
    London:  07:00 - 16:00 UTC
    NY:      12:00 - 21:00 UTC
    Overlap: London-NY (12:00 - 16:00) reported as OVERLAP.
    Otherwise QUIET.
    """
    h = asof_utc.hour
    if 12 <= h < 16:
        return "OVERLAP"
    if 7 <= h < 12:
        return "LONDON"
    if 16 <= h < 21:
        return "NY"
    if 0 <= h < 8:
        return "TOKYO"
    return "QUIET"


def build_market_pack_v2(
    *,
    symbol: str,
    asof_utc: datetime,
    candles: list[Candle],
    pivots: list[PivotPointV2],
    atr_m5_14: float,
    atr_h1_14: float | None = None,
    atr_h4_14: float | None = None,
    high_24h: float,
    low_24h: float,
    high_1w: float | None = None,
    low_1w: float | None = None,
    calendar_events_within_60min: list[CalendarEvent] | None = None,
    current_price: float,
    current_spread: float | None = None,
) -> MarketAnalysisPackV2:
    """Assemble a v2 pack from already-computed numeric facts.

    The function intentionally does **not** call any pattern detector or
    line builder. Higher layers compute pivots/ATR/etc. and pass them in.
    """
    return MarketAnalysisPackV2(
        symbol=symbol,
        asof_utc=asof_utc,
        candles=candles,
        pivots=pivots,
        atr=AtrPack(m5_14=atr_m5_14, h1_14=atr_h1_14, h4_14=atr_h4_14),
        recent_range=RangePack(
            high_24h=high_24h,
            low_24h=low_24h,
            high_1w=high_1w,
            low_1w=low_1w,
        ),
        calendar_events_within_60min=list(calendar_events_within_60min or []),
        current_price=current_price,
        current_spread=current_spread,
        session=_classify_session(asof_utc),
    )


__all__ = [
    "AtrPack",
    "RangePack",
    "CalendarEvent",
    "MarketAnalysisPackV2",
    "build_market_pack_v2",
    "SessionLabel",
]
