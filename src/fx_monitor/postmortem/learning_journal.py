"""Aggregate post-mortems over time to surface recurring failure patterns.

This is what powers the monthly "what's the AI consistently getting
wrong, and what should we change?" review. It runs over the corpus,
classifies each non-trivial outcome via :func:`postmortem.analyzer.analyze`,
and reports counts per failure mode plus the most-suggested
countermeasures.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Callable

from pydantic import BaseModel, Field

from fx_monitor.corpus.schema import CorpusEntry
from fx_monitor.live.candle import Candle

from .analyzer import Postmortem, analyze


FetchFutureFn = Callable[[str, datetime, int], list[Candle]]


class LearningJournalEntry(BaseModel):
    entry_id: str
    asof_utc: datetime
    side: str
    final_status: str
    outcome_status: str
    failure_mode: str
    severity: str
    headline_ja: str
    countermeasures_ja: list[str] = Field(default_factory=list)


class LearningJournal(BaseModel):
    schema_version: str = "learning_journal_v1"
    generated_at_utc: datetime
    window_days: int
    total_examined: int
    actionable_entries: list[LearningJournalEntry] = Field(default_factory=list)
    failure_mode_counts: dict[str, int] = Field(default_factory=dict)
    countermeasure_frequency: dict[str, int] = Field(default_factory=dict)


def build_learning_journal(
    entries: list[CorpusEntry],
    *,
    fetch_future: FetchFutureFn,
    window_days: int = 30,
    lookahead_bars: int = 60,
    now_utc: datetime | None = None,
) -> LearningJournal:
    now = now_utc or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)

    actionable: list[LearningJournalEntry] = []
    fm_counter: Counter[str] = Counter()
    cm_counter: Counter[str] = Counter()
    examined = 0

    for entry in entries:
        asof = entry.asof_utc if entry.asof_utc.tzinfo else entry.asof_utc.replace(tzinfo=timezone.utc)
        if asof < cutoff:
            continue
        examined += 1
        future = fetch_future(entry.symbol, asof, lookahead_bars)
        pm = analyze(entry, future)
        if pm.failure_mode in ("no_post_mortem_needed", "outcome_pending"):
            continue
        actionable.append(
            LearningJournalEntry(
                entry_id=entry.entry_id,
                asof_utc=asof,
                side=entry.judgement.side,
                final_status=entry.judgement.final_status,
                outcome_status=entry.outcome.status,
                failure_mode=pm.failure_mode,
                severity=pm.severity,
                headline_ja=pm.headline_ja,
                countermeasures_ja=pm.countermeasures_ja,
            )
        )
        fm_counter[pm.failure_mode] += 1
        for cm in pm.countermeasures_ja:
            cm_counter[cm] += 1

    return LearningJournal(
        generated_at_utc=now,
        window_days=window_days,
        total_examined=examined,
        actionable_entries=actionable,
        failure_mode_counts=dict(fm_counter),
        countermeasure_frequency=dict(cm_counter),
    )


__all__ = ["build_learning_journal", "LearningJournal", "LearningJournalEntry"]
