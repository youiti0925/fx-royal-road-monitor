"""Lightweight corpus storage.

Design constraints:

- Zero external services. Pure files in ``data/``.
- Thousands of entries comfortably; tens of thousands acceptable.
- Linear cosine search via numpy. At ~10k entries this runs in a few
  milliseconds, well under any AI inference latency.
- Append-only on the happy path; updates rewrite the JSONL file.

Layout:

    data/corpus/<name>/entries.jsonl   one CorpusEntry JSON per line
    data/corpus/<name>/vectors.npy     vectors[i] corresponds to entries[i]

If the two files disagree on length we rebuild ``vectors.npy`` from
``entries.jsonl`` on next load.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np

from .schema import CorpusEntry, OutcomeLabel
from .entry_validator import validate_entry, CorpusValidationError


class JsonlVectorStore:
    """Append-only-ish corpus store with linear cosine retrieval."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.entries_path = self.root / "entries.jsonl"
        self.vectors_path = self.root / "vectors.npy"
        self._entries: list[CorpusEntry] = []
        self._vectors: np.ndarray | None = None
        self._load()

    # ---- persistence ----

    def _load(self) -> None:
        if not self.entries_path.exists():
            self._entries = []
            self._vectors = None
            return
        entries: list[CorpusEntry] = []
        with self.entries_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                entries.append(CorpusEntry.model_validate_json(line))
        self._entries = entries
        if self.vectors_path.exists():
            try:
                vectors = np.load(self.vectors_path)
                if vectors.shape[0] == len(entries):
                    self._vectors = vectors
                    return
            except Exception:
                pass
        self._rebuild_vectors()

    def _rebuild_vectors(self) -> None:
        if not self._entries:
            self._vectors = None
            return
        dim = len(self._entries[0].feature_vector)
        arr = np.zeros((len(self._entries), dim), dtype=np.float64)
        for i, e in enumerate(self._entries):
            arr[i] = e.feature_vector
        self._vectors = arr
        np.save(self.vectors_path, arr)

    def _persist_all(self) -> None:
        with self.entries_path.open("w", encoding="utf-8") as fh:
            for e in self._entries:
                fh.write(e.model_dump_json() + "\n")
        self._rebuild_vectors()

    def _append_one(self, entry: CorpusEntry) -> None:
        with self.entries_path.open("a", encoding="utf-8") as fh:
            fh.write(entry.model_dump_json() + "\n")
        self._entries.append(entry)
        v = np.asarray(entry.feature_vector, dtype=np.float64)[None, :]
        if self._vectors is None:
            self._vectors = v
        else:
            self._vectors = np.vstack([self._vectors, v])
        np.save(self.vectors_path, self._vectors)

    # ---- mutations ----

    def add(self, entry: CorpusEntry, *, skip_validation: bool = False) -> None:
        if any(e.entry_id == entry.entry_id for e in self._entries):
            raise ValueError(f"duplicate entry_id: {entry.entry_id}")
        if not skip_validation:
            issues = validate_entry(entry)
            if issues:
                raise CorpusValidationError(entry.entry_id, issues)
        self._append_one(entry)

    def update_outcome(self, entry_id: str, outcome: OutcomeLabel) -> bool:
        for i, e in enumerate(self._entries):
            if e.entry_id == entry_id:
                self._entries[i] = e.model_copy(update={"outcome": outcome})
                self._persist_all()
                return True
        return False

    def mark_dissent(
        self,
        entry_id: str,
        *,
        note: str | None = None,
        at_utc: datetime | None = None,
    ) -> bool:
        for i, e in enumerate(self._entries):
            if e.entry_id == entry_id:
                self._entries[i] = e.model_copy(
                    update={
                        "user_dissent": True,
                        "user_dissent_note": note,
                        "user_dissent_at_utc": at_utc or datetime.utcnow(),
                    }
                )
                self._persist_all()
                return True
        return False

    # ---- reads ----

    def __len__(self) -> int:
        return len(self._entries)

    def all(self) -> list[CorpusEntry]:
        return list(self._entries)

    def pending_outcomes(self) -> list[CorpusEntry]:
        return [e for e in self._entries if e.outcome.status == "PENDING"]

    def get(self, entry_id: str) -> CorpusEntry | None:
        for e in self._entries:
            if e.entry_id == entry_id:
                return e
        return None

    def search_similar(
        self,
        query_vector: np.ndarray | list[float],
        *,
        top_k: int = 10,
        outcome_filter: tuple[str, ...] | None = ("WIN", "LOSE", "NEUTRAL_GOOD", "NEUTRAL_MISSED"),
        recency_weight: float = 0.0,
        now_utc: datetime | None = None,
        session_filter: str | None = None,
        symbol_filter: str | None = None,
        side_filter: tuple[str, ...] | None = None,
        has_high_impact_event: bool | None = None,
    ) -> list[tuple[float, CorpusEntry]]:
        """Return up to ``top_k`` (similarity, entry) pairs.

        Similarity is cosine in [-1, 1], optionally biased toward recent
        entries by ``recency_weight``: a half-life-like multiplier where
        a bigger weight pulls older entries down. ``recency_weight=0``
        disables the boost (purely cosine ranking).

        v6 adds metadata filters that compose with the cosine score so
        the caller can ask for "similar AND outcome=WIN" or "similar AND
        same session as now".
        """
        if self._vectors is None or len(self._entries) == 0:
            return []
        q = np.asarray(query_vector, dtype=np.float64)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return []

        norms = np.linalg.norm(self._vectors, axis=1)
        safe_norms = np.where(norms == 0, 1.0, norms)
        sims = (self._vectors @ q) / (safe_norms * q_norm)
        sims = np.where(norms == 0, -1.0, sims)

        scores = sims.copy()
        if recency_weight > 0 and now_utc is not None:
            ages_days = np.array(
                [
                    max((now_utc - e.asof_utc).total_seconds() / 86400.0, 0.0)
                    for e in self._entries
                ]
            )
            decay = np.exp(-recency_weight * ages_days / 90.0)
            scores = scores * decay

        eligible_idx = list(range(len(self._entries)))
        if outcome_filter is not None:
            eligible_idx = [
                i for i in eligible_idx
                if self._entries[i].outcome.status in outcome_filter
            ]
        if session_filter is not None:
            eligible_idx = [
                i for i in eligible_idx
                if self._entries[i].market_pack.session == session_filter
            ]
        if symbol_filter is not None:
            eligible_idx = [
                i for i in eligible_idx
                if self._entries[i].symbol == symbol_filter
            ]
        if side_filter is not None:
            eligible_idx = [
                i for i in eligible_idx
                if self._entries[i].judgement.side in side_filter
            ]
        if has_high_impact_event is not None:
            def _has_high(idx: int) -> bool:
                evs = self._entries[idx].market_pack.calendar_events_within_60min
                return any(e.impact == "HIGH" for e in evs)

            eligible_idx = [
                i for i in eligible_idx
                if _has_high(i) == has_high_impact_event
            ]
        if not eligible_idx:
            return []
        eligible_idx.sort(key=lambda i: scores[i], reverse=True)
        chosen = eligible_idx[:top_k]
        return [(float(sims[i]), self._entries[i]) for i in chosen]

    def search_visual_similar(
        self,
        clip_query_vector: np.ndarray | list[float],
        *,
        top_k: int = 5,
        outcome_filter: tuple[str, ...] | None = ("WIN", "LOSE", "NEUTRAL_GOOD", "NEUTRAL_MISSED"),
    ) -> list[tuple[float, CorpusEntry]]:
        """Visual similarity search using CLIP embeddings.

        Iterates only over entries that have a stored ``clip_vector``.
        Returns the top-k entries by cosine similarity in 512-dim CLIP
        space. CLIP captures chart pattern gestalt (double top,
        ascending triangle, etc.) that the 272-dim numeric vector
        cannot.
        """
        if not self._entries:
            return []
        q = np.asarray(clip_query_vector, dtype=np.float64)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return []
        scored: list[tuple[float, CorpusEntry]] = []
        for entry in self._entries:
            if entry.clip_vector is None:
                continue
            if outcome_filter is not None and entry.outcome.status not in outcome_filter:
                continue
            cv = np.asarray(entry.clip_vector, dtype=np.float64)
            cv_norm = np.linalg.norm(cv)
            if cv_norm == 0:
                continue
            sim = float((q @ cv) / (q_norm * cv_norm))
            scored.append((sim, entry))
        scored.sort(key=lambda t: t[0], reverse=True)
        return scored[:top_k]

    def search_multi_mode(
        self,
        query_vector: np.ndarray | list[float],
        *,
        top_k_per_mode: int = 5,
        symbol: str | None = None,
        session: str | None = None,
        has_high_impact_event: bool | None = None,
        clip_query_vector: np.ndarray | list[float] | None = None,
        now_utc: datetime | None = None,
    ) -> dict[str, list[tuple[float, CorpusEntry]]]:
        """Run the v6 multi-mode retrieval suite in one call.

        Returns a dict with keys:

        - ``generic``: classic cosine-similar entries (any outcome).
        - ``win_only``: similar entries that ended in WIN.
        - ``lose_only``: similar entries that ended in LOSE.
        - ``same_htf_context``: similar entries with same session
          (proxy for HTF/regime context until W1/D1 bias is encoded).
        - ``same_fundamentals``: similar entries with the same
          high-impact-event flag as the query.
        """
        common: dict = {
            "top_k": top_k_per_mode,
            "now_utc": now_utc,
            "recency_weight": 0.5,
        }
        if symbol is not None:
            common["symbol_filter"] = symbol

        results: dict[str, list[tuple[float, CorpusEntry]]] = {}
        results["generic"] = self.search_similar(query_vector, **common)
        results["win_only"] = self.search_similar(
            query_vector, outcome_filter=("WIN",), **common
        )
        results["lose_only"] = self.search_similar(
            query_vector, outcome_filter=("LOSE",), **common
        )
        if session is not None:
            results["same_htf_context"] = self.search_similar(
                query_vector, session_filter=session, **common
            )
        else:
            results["same_htf_context"] = []
        if has_high_impact_event is not None:
            results["same_fundamentals"] = self.search_similar(
                query_vector,
                has_high_impact_event=has_high_impact_event,
                **common,
            )
        else:
            results["same_fundamentals"] = []
        if clip_query_vector is not None:
            results["visual_similar"] = self.search_visual_similar(
                clip_query_vector, top_k=top_k_per_mode,
            )
            results["visual_win_only"] = self.search_visual_similar(
                clip_query_vector, top_k=top_k_per_mode, outcome_filter=("WIN",),
            )
            results["visual_lose_only"] = self.search_visual_similar(
                clip_query_vector, top_k=top_k_per_mode, outcome_filter=("LOSE",),
            )
        else:
            results["visual_similar"] = []
            results["visual_win_only"] = []
            results["visual_lose_only"] = []
        return results


__all__ = ["JsonlVectorStore"]
