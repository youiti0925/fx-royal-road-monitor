"""Resumable batch runner that drives offline corpus construction.

Orchestrates: archive walk -> candidate filter -> AI judge -> outcome
fill -> corpus.add. The AI judge is injected as a callable so the
runner is testable without any real AI call.

Pacing knobs are explicit:
- ``batch_size`` caps how many candidates we process per invocation
  (one Claude Code session ~ one invocation).
- ``pacing_seconds_between`` adds a sleep between AI calls; the runner
  is meant to look interactive, not like a tight automation loop.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from fx_monitor.ai.decision_screen_spec_schema import AiDecisionScreenSpec
from fx_monitor.ai.prompt_builder_v2 import (
    BuiltPrompt,
    build_decision_prompt,
    load_knowledge_pack,
)
from fx_monitor.corpus.outcome import compute_outcome
from fx_monitor.corpus.schema import CorpusEntry, OutcomeLabel
from fx_monitor.corpus.store import JsonlVectorStore
from fx_monitor.live.atr import atr
from fx_monitor.live.candle import Candle
from fx_monitor.live.embedding import chart_pack_to_vector
from fx_monitor.live.market_pack_v2 import (
    MarketAnalysisPackV2,
    build_market_pack_v2,
)
from fx_monitor.live.pivots_v2 import detect_multi_scale_pivots
from fx_monitor.live.post_validate import post_validate

from .candidate_filter import is_candidate
from .progress_state import ProgressState


JudgeFn = Callable[[BuiltPrompt], AiDecisionScreenSpec]


@dataclass
class BatchResult:
    processed: int
    errors: int
    remaining: int
    total_candidates: int


def _select_candidates(
    candles: list[Candle],
    *,
    window_size: int,
    step: int,
) -> list[int]:
    """Walk the archive and return indices that pass :func:`is_candidate`.

    The returned ``index`` is the **anchor** index — the index of the
    last candle in the window (i.e. the candle the judge sees as
    ``current``).
    """
    out: list[int] = []
    if len(candles) < window_size + 1:
        return out
    for i in range(window_size, len(candles), step):
        window = candles[i - window_size : i]
        if is_candidate(window).is_candidate:
            out.append(i)
    return out


def _build_pack_at_anchor(
    *,
    candles: list[Candle],
    anchor_index: int,
    symbol: str,
    window_size: int,
) -> MarketAnalysisPackV2:
    window = candles[max(0, anchor_index - window_size) : anchor_index]
    asof = window[-1].t if window else candles[anchor_index - 1].t
    atr_m5 = atr(window, period=14)
    pivots = detect_multi_scale_pivots(window, atr_m5=atr_m5)
    return build_market_pack_v2(
        symbol=symbol,
        asof_utc=asof,
        candles=window,
        pivots=pivots,
        atr_m5_14=atr_m5,
        high_24h=max(c.h for c in window),
        low_24h=min(c.l for c in window),
        current_price=window[-1].c,
    )


def run_batch(
    *,
    candles: list[Candle],
    symbol: str,
    timeframe: str,
    judge_fn: JudgeFn,
    store: JsonlVectorStore,
    progress_path: Path | str,
    batch_size: int = 30,
    window_size: int = 60,
    step: int = 1,
    outcome_lookahead_bars: int = 60,
    pacing_seconds_between: float = 0.0,
    knowledge_pack_path: Path | str | None = None,
    retrieval_top_k: int = 10,
    now_utc: datetime | None = None,
) -> BatchResult:
    """Process up to ``batch_size`` pending candidates.

    The function is designed to be called many times in succession. Each
    call advances the persisted progress file and the corpus store, so
    interrupting and restarting is safe.
    """
    if not candles:
        return BatchResult(0, 0, 0, 0)

    progress = ProgressState.load_or_init(
        progress_path,
        symbol=symbol,
        timeframe=timeframe,
        start_utc=candles[0].t,
        end_utc=candles[-1].t,
    )
    candidates = _select_candidates(candles, window_size=window_size, step=step)
    progress.total_candidates = len(candidates)

    pending = [i for i in candidates if not progress.is_done(i)]
    this_batch = pending[:batch_size]

    knowledge_pack = load_knowledge_pack(knowledge_pack_path)

    processed = 0
    errors = 0
    for anchor_index in this_batch:
        try:
            pack = _build_pack_at_anchor(
                candles=candles,
                anchor_index=anchor_index,
                symbol=symbol,
                window_size=window_size,
            )
            vector = chart_pack_to_vector(pack)

            retrieved = store.search_similar(
                vector,
                top_k=retrieval_top_k,
                now_utc=now_utc or pack.asof_utc,
                recency_weight=0.5,
            )

            prompt = build_decision_prompt(
                pack,
                retrieved=retrieved,
                knowledge_pack=knowledge_pack,
                knowledge_pack_path=knowledge_pack_path,
            )
            spec = judge_fn(prompt)

            validation = post_validate(spec, pack)
            if validation.downgraded:
                spec = spec.model_copy(update={"final_status": "UNKNOWN"})

            future = candles[anchor_index : anchor_index + outcome_lookahead_bars]
            entry = CorpusEntry(
                entry_id=str(uuid.uuid4()),
                asof_utc=pack.asof_utc,
                symbol=symbol,
                timeframe=timeframe,
                source="offline_batch",
                market_pack=pack,
                feature_vector=vector.tolist(),
                judgement=spec,
                judgement_at_utc=datetime.now(timezone.utc),
            )
            outcome = compute_outcome(
                entry,
                future,
                max_bars=outcome_lookahead_bars,
            )
            entry = entry.model_copy(update={"outcome": outcome})
            store.add(entry)
            progress.mark_done(anchor_index)
            processed += 1
        except Exception as exc:  # pragma: no cover - exercised via test
            progress.mark_error(anchor_index, repr(exc))
            errors += 1
        progress.save(progress_path)
        if pacing_seconds_between > 0:
            time.sleep(pacing_seconds_between)

    progress.session_finalise(processed)
    progress.save(progress_path)

    return BatchResult(
        processed=processed,
        errors=errors,
        remaining=max(len(pending) - len(this_batch), 0),
        total_candidates=len(candidates),
    )


__all__ = ["run_batch", "BatchResult", "JudgeFn"]
