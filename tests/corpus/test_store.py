from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from fx_monitor.ai.decision_screen_spec_schema import AiDecisionScreenSpec
from fx_monitor.corpus.schema import CorpusEntry, OutcomeLabel
from fx_monitor.corpus.store import JsonlVectorStore
from fx_monitor.live.market_pack_v2 import (
    AtrPack,
    MarketAnalysisPackV2,
    RangePack,
)


def _entry(
    entry_id: str,
    *,
    asof: datetime | None = None,
    vector: list[float] | None = None,
    outcome_status: str = "PENDING",
) -> CorpusEntry:
    asof = asof or datetime(2026, 5, 4, 13, 0, tzinfo=timezone.utc)
    pack = MarketAnalysisPackV2(
        symbol="EURUSD=X",
        asof_utc=asof,
        candles=[],
        pivots=[],
        atr=AtrPack(m5_14=0.001),
        recent_range=RangePack(high_24h=1.20, low_24h=1.09),
        current_price=1.12,
        session="OVERLAP",
    )
    spec = AiDecisionScreenSpec(
        provider="claude",
        symbol="EURUSD=X",
        timeframe="M5",
    )
    return CorpusEntry(
        entry_id=entry_id,
        asof_utc=asof,
        symbol="EURUSD=X",
        timeframe="M5",
        source="live_recorded",
        market_pack=pack,
        feature_vector=vector if vector is not None else [1.0, 0.0, 0.0, 0.0],
        judgement=spec,
        judgement_at_utc=asof,
        outcome=OutcomeLabel(status=outcome_status),  # type: ignore[arg-type]
    )


def test_empty_store_search_returns_empty(tmp_path: Path):
    store = JsonlVectorStore(tmp_path / "c1")
    assert len(store) == 0
    assert store.search_similar([1.0, 0.0, 0.0, 0.0]) == []


def test_add_persists_across_reload(tmp_path: Path):
    root = tmp_path / "c2"
    s1 = JsonlVectorStore(root)
    s1.add(_entry("a", outcome_status="WIN", vector=[1.0, 0.0, 0.0, 0.0]), skip_validation=True)
    s1.add(_entry("b", outcome_status="LOSE", vector=[0.0, 1.0, 0.0, 0.0]), skip_validation=True)

    s2 = JsonlVectorStore(root)
    assert len(s2) == 2
    assert s2.get("a") is not None
    assert s2.get("b") is not None


def test_duplicate_entry_id_rejected(tmp_path: Path):
    store = JsonlVectorStore(tmp_path / "c3")
    store.add(_entry("dup"), skip_validation=True)
    with pytest.raises(ValueError):
        store.add(_entry("dup"), skip_validation=True)


def test_search_returns_top_k_in_similarity_order(tmp_path: Path):
    store = JsonlVectorStore(tmp_path / "c4")
    store.add(_entry("close", outcome_status="WIN", vector=[1.0, 0.1, 0.0, 0.0]), skip_validation=True)
    store.add(_entry("medium", outcome_status="WIN", vector=[1.0, 1.0, 0.0, 0.0]), skip_validation=True)
    store.add(_entry("far", outcome_status="WIN", vector=[0.0, 0.0, 1.0, 0.0]), skip_validation=True)

    results = store.search_similar([1.0, 0.0, 0.0, 0.0], top_k=2)
    assert len(results) == 2
    assert [e.entry_id for _, e in results] == ["close", "medium"]


def test_search_excludes_pending_outcomes_by_default(tmp_path: Path):
    store = JsonlVectorStore(tmp_path / "c5")
    store.add(_entry("ready", outcome_status="WIN", vector=[1.0, 0.0, 0.0, 0.0]), skip_validation=True)
    store.add(_entry("waiting", outcome_status="PENDING", vector=[1.0, 0.0, 0.0, 0.0]), skip_validation=True)

    results = store.search_similar([1.0, 0.0, 0.0, 0.0], top_k=10)
    assert [e.entry_id for _, e in results] == ["ready"]


def test_update_outcome_changes_status(tmp_path: Path):
    store = JsonlVectorStore(tmp_path / "c6")
    store.add(_entry("p1", outcome_status="PENDING"), skip_validation=True)
    new_outcome = OutcomeLabel(
        status="WIN",
        max_favorable_pip=42.0,
        bars_observed=60,
        filled_at_utc=datetime(2026, 5, 4, 18, 0, tzinfo=timezone.utc),
    )
    assert store.update_outcome("p1", new_outcome) is True

    s2 = JsonlVectorStore(tmp_path / "c6")
    e = s2.get("p1")
    assert e is not None
    assert e.outcome.status == "WIN"
    assert e.outcome.max_favorable_pip == 42.0


def test_pending_outcomes_filter(tmp_path: Path):
    store = JsonlVectorStore(tmp_path / "c7")
    store.add(_entry("p", outcome_status="PENDING"), skip_validation=True)
    store.add(_entry("d", outcome_status="WIN"), skip_validation=True)
    pending = store.pending_outcomes()
    assert [e.entry_id for e in pending] == ["p"]


def test_mark_dissent_sets_flag(tmp_path: Path):
    store = JsonlVectorStore(tmp_path / "c8")
    store.add(_entry("z", outcome_status="WIN"), skip_validation=True)
    assert store.mark_dissent("z", note="上位足と矛盾") is True
    e = store.get("z")
    assert e is not None
    assert e.user_dissent is True
    assert e.user_dissent_note == "上位足と矛盾"


def test_recency_weight_promotes_recent_entries(tmp_path: Path):
    store = JsonlVectorStore(tmp_path / "c9")
    now = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    # Two entries with identical vectors. The recent one should win when
    # recency_weight is large.
    store.add(
        _entry("old", asof=now - timedelta(days=180), outcome_status="WIN", vector=[1.0, 0.0, 0.0, 0.0]), skip_validation=True)
    store.add(
        _entry("new", asof=now - timedelta(days=1), outcome_status="WIN", vector=[1.0, 0.0, 0.0, 0.0]), skip_validation=True)
    results = store.search_similar(
        [1.0, 0.0, 0.0, 0.0],
        top_k=2,
        recency_weight=2.0,
        now_utc=now,
    )
    assert results[0][1].entry_id == "new"


def test_search_multi_mode_returns_all_buckets(tmp_path: Path):
    store = JsonlVectorStore(tmp_path / "c11")
    store.add(_entry("a", outcome_status="WIN"), skip_validation=True)
    store.add(_entry("b", outcome_status="LOSE"), skip_validation=True)
    store.add(_entry("c", outcome_status="NEUTRAL_GOOD"), skip_validation=True)

    modes = store.search_multi_mode(
        [1.0, 0.0, 0.0, 0.0],
        top_k_per_mode=5,
        session="OVERLAP",
        has_high_impact_event=False,
    )
    assert "generic" in modes
    assert "win_only" in modes
    assert "lose_only" in modes
    assert "same_htf_context" in modes
    assert "same_fundamentals" in modes
    win_ids = {e.entry_id for _, e in modes["win_only"]}
    assert win_ids == {"a"}
    lose_ids = {e.entry_id for _, e in modes["lose_only"]}
    assert lose_ids == {"b"}


def test_search_with_session_filter(tmp_path: Path):
    store = JsonlVectorStore(tmp_path / "c12")
    e1 = _entry("a", outcome_status="WIN")
    # Override session via direct field: we mutate the validated model.
    e1 = e1.model_copy(
        update={"market_pack": e1.market_pack.model_copy(update={"session": "TOKYO"})}
    )
    e2 = _entry("b", outcome_status="WIN")
    e2 = e2.model_copy(
        update={"market_pack": e2.market_pack.model_copy(update={"session": "LONDON"})}
    )
    store.add(e1, skip_validation=True)
    store.add(e2, skip_validation=True)
    london_only = store.search_similar(
        [1.0, 0.0, 0.0, 0.0], top_k=5, session_filter="LONDON"
    )
    ids = {e.entry_id for _, e in london_only}
    assert ids == {"b"}


def test_vector_file_rebuilt_when_out_of_sync(tmp_path: Path):
    root = tmp_path / "c10"
    s1 = JsonlVectorStore(root)
    s1.add(_entry("a", outcome_status="WIN", vector=[1.0, 0.0, 0.0, 0.0]), skip_validation=True)
    # Corrupt the vectors file.
    (root / "vectors.npy").write_bytes(b"garbage")
    s2 = JsonlVectorStore(root)
    assert len(s2) == 1
    results = s2.search_similar([1.0, 0.0, 0.0, 0.0])
    assert results
