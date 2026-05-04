"""Resumable batch progress state.

The batch runner is invoked many times across many sessions. We persist
which candidate indices have been processed (with their per-entry
results) so a subsequent invocation picks up exactly where the previous
one stopped.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ProgressError(BaseModel):
    index: int
    reason: str
    occurred_at_utc: datetime


class ProgressState(BaseModel):
    schema_version: Literal["build_corpus_progress_v1"] = "build_corpus_progress_v1"
    symbol: str
    timeframe: str
    start_utc: datetime
    end_utc: datetime
    total_candidates: int = 0
    processed_indices: list[int] = Field(default_factory=list)
    last_session_at_utc: datetime | None = None
    last_session_processed_count: int = 0
    errors: list[ProgressError] = Field(default_factory=list)

    @classmethod
    def load_or_init(
        cls,
        path: Path | str,
        *,
        symbol: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> "ProgressState":
        p = Path(path)
        if p.exists():
            data = p.read_text(encoding="utf-8")
            state = cls.model_validate_json(data)
            if (
                state.symbol != symbol
                or state.timeframe != timeframe
                or state.start_utc != start_utc
                or state.end_utc != end_utc
            ):
                raise ValueError(
                    "progress file mismatches requested job parameters; "
                    "delete the file or use a different output path"
                )
            return state
        p.parent.mkdir(parents=True, exist_ok=True)
        return cls(
            symbol=symbol,
            timeframe=timeframe,
            start_utc=start_utc,
            end_utc=end_utc,
        )

    def save(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    def mark_done(self, index: int) -> None:
        if index not in self.processed_indices:
            self.processed_indices.append(index)

    def mark_error(self, index: int, reason: str) -> None:
        self.errors.append(
            ProgressError(
                index=index,
                reason=reason,
                occurred_at_utc=datetime.now(timezone.utc),
            )
        )

    def is_done(self, index: int) -> bool:
        return index in self.processed_indices

    def session_finalise(self, processed_count: int) -> None:
        self.last_session_at_utc = datetime.now(timezone.utc)
        self.last_session_processed_count = processed_count


__all__ = ["ProgressState", "ProgressError"]
