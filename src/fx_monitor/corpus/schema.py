"""Corpus entry and outcome schemas.

A :class:`CorpusEntry` records exactly what we knew at the moment of a
judgement plus what actually happened in the next 60 bars. Older entries
are the raw material for retrieval-augmented prompts, so the schema
needs every field a future prompt builder might want.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from fx_monitor.ai.decision_screen_spec_schema import AiDecisionScreenSpec
from fx_monitor.live.market_pack_v2 import MarketAnalysisPackV2

OutcomeStatus = Literal[
    "PENDING",
    "WIN",
    "LOSE",
    "NEUTRAL_GOOD",
    "NEUTRAL_MISSED",
]

EntrySource = Literal["offline_batch", "live_recorded"]


class OutcomeLabel(BaseModel):
    """Machine-derived outcome for a judgement.

    All numbers are reported in pip (a single price unit defined by the
    symbol's pip size). Sign convention: positive = price moved in the
    direction the AI argued for; negative = against.
    """

    schema_version: Literal["outcome_label_v1"] = "outcome_label_v1"
    status: OutcomeStatus
    max_favorable_pip: float | None = None
    max_adverse_pip: float | None = None
    close_diff_pip: float | None = None
    bars_observed: int = 0
    filled_at_utc: datetime | None = None


class CorpusEntry(BaseModel):
    """One row of the past-judgement corpus."""

    schema_version: Literal["corpus_entry_v1"] = "corpus_entry_v1"
    entry_id: str
    asof_utc: datetime
    symbol: str
    timeframe: str
    source: EntrySource

    market_pack: MarketAnalysisPackV2
    feature_vector: list[float]
    clip_vector: list[float] | None = None  # v7: CLIP visual embedding

    judgement: AiDecisionScreenSpec
    judgement_model: str = "claude-code-via-subscription"
    judgement_at_utc: datetime

    outcome: OutcomeLabel = Field(default_factory=lambda: OutcomeLabel(status="PENDING"))

    user_dissent: bool = False
    user_dissent_note: str | None = None
    user_dissent_at_utc: datetime | None = None


__all__ = ["CorpusEntry", "OutcomeLabel", "OutcomeStatus", "EntrySource"]
