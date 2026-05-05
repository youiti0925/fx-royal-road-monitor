from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fx_monitor.ai.decision_screen_spec_schema import AiDecisionScreenSpec
from fx_monitor.ai.prompt_builder_v2 import BuiltPrompt
from fx_monitor.corpus.store import JsonlVectorStore
from fx_monitor.live.candle import Candle
from fx_monitor.offline.batch_runner import run_batch


def _build_archive(n: int = 200) -> list[Candle]:
    """Build a synthetic archive with a few injected swings.

    The default 200 bars cover enough history for the candidate filter
    to fire on at least a handful of indices.
    """
    out: list[Candle] = []
    for i in range(n):
        # Slow base trend + sinusoidal swings + per-block step changes.
        base = 1.10 + 0.0001 * i
        wave = 0.005 * math.sin(i / 7.0)
        block = 0.003 if (i // 30) % 2 == 0 else -0.003
        mid = base + wave + block
        h = mid + 0.0008
        lo = mid - 0.0008
        out.append(
            Candle(
                t=datetime.fromtimestamp(i * 300, tz=timezone.utc),
                o=mid,
                h=h,
                l=lo,
                c=mid,
                v=100.0 + (i % 7),
            )
        )
    return out


def _judge_factory(side: str = "SELL", final_status: str = "WAIT_BREAKOUT"):
    def _judge(prompt: BuiltPrompt) -> AiDecisionScreenSpec:
        return AiDecisionScreenSpec(
            provider="claude",
            symbol="EURUSD=X",
            timeframe="M5",
            side=side,  # type: ignore[arg-type]
            final_status=final_status,  # type: ignore[arg-type]
            summary_ja="test judgement",
        )

    return _judge


def test_run_batch_processes_up_to_batch_size(tmp_path: Path):
    candles = _build_archive(200)
    store = JsonlVectorStore(tmp_path / "corpus")
    progress_path = tmp_path / "progress.json"

    result = run_batch(
        candles=candles,
        symbol="EURUSD=X",
        timeframe="M5",
        judge_fn=_judge_factory(),
        store=store,
        progress_path=progress_path,
        batch_size=5,
        window_size=60,
        step=10,
     skip_corpus_validation=True,)

    assert result.processed <= 5
    assert result.processed > 0
    assert len(store) == result.processed


def test_run_batch_resumes_from_progress(tmp_path: Path):
    candles = _build_archive(200)
    store = JsonlVectorStore(tmp_path / "corpus")
    progress_path = tmp_path / "progress.json"
    judge = _judge_factory()

    first = run_batch(
        candles=candles,
        symbol="EURUSD=X",
        timeframe="M5",
        judge_fn=judge,
        store=store,
        progress_path=progress_path,
        batch_size=3,
        window_size=60,
        step=10,
     skip_corpus_validation=True,)
    second = run_batch(
        candles=candles,
        symbol="EURUSD=X",
        timeframe="M5",
        judge_fn=judge,
        store=store,
        progress_path=progress_path,
        batch_size=3,
        window_size=60,
        step=10,
     skip_corpus_validation=True,)

    assert second.processed > 0
    assert first.processed + second.processed == len(store)


def test_run_batch_records_errors_without_aborting(tmp_path: Path):
    candles = _build_archive(200)
    store = JsonlVectorStore(tmp_path / "corpus")
    progress_path = tmp_path / "progress.json"

    call_count = {"n": 0}

    def flaky_judge(prompt: BuiltPrompt) -> AiDecisionScreenSpec:
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated failure")
        return AiDecisionScreenSpec(
            provider="claude",
            symbol="EURUSD=X",
            timeframe="M5",
            side="SELL",
            final_status="WAIT_BREAKOUT",
            summary_ja="ok",
        )

    result = run_batch(
        candles=candles,
        symbol="EURUSD=X",
        timeframe="M5",
        judge_fn=flaky_judge,
        store=store,
        progress_path=progress_path,
        batch_size=4,
        window_size=60,
        step=10,
     skip_corpus_validation=True,)
    assert result.errors == 1
    assert result.processed == result.processed  # tautology, but we want progress > 0
    assert result.processed >= 1


def test_run_batch_outcome_is_filled_for_internal_anchors(tmp_path: Path):
    candles = _build_archive(300)
    store = JsonlVectorStore(tmp_path / "corpus")
    progress_path = tmp_path / "progress.json"

    run_batch(
        candles=candles,
        symbol="EURUSD=X",
        timeframe="M5",
        judge_fn=_judge_factory(),
        store=store,
        progress_path=progress_path,
        batch_size=5,
        window_size=60,
        step=20,
        outcome_lookahead_bars=30,
     skip_corpus_validation=True,)

    for entry in store.all():
        # Anchor indices were chosen so that 30+ future bars exist.
        assert entry.outcome.bars_observed > 0
        assert entry.outcome.status != "PENDING"
