"""Prepare the prompt for ``/royal-road-check``.

Builds a MarketAnalysisPackV2 from the most recent OHLC, retrieves
similar past entries from the corpus, and writes:

- ``data/pending_judgements/<id>.json``: the pack + retrieved IDs
- ``data/pending_judgements/<id>.prompt.md``: human/AI-readable prompt

Claude Code then reads the prompt file, produces an
AiDecisionScreenSpec JSON, and calls ``check_finalise`` with the spec.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fx_monitor.ai.prompt_builder_v2 import build_decision_prompt
from fx_monitor.corpus.store import JsonlVectorStore
from fx_monitor.live.atr import atr
from fx_monitor.live.candle import Candle
from fx_monitor.live.embedding import chart_pack_to_vector
from fx_monitor.live.market_pack_v2 import build_market_pack_v2
from fx_monitor.live.pivots_v2 import detect_multi_scale_pivots
from fx_monitor.offline.ohlc_archive import load_ohlc_records

from ._paths import (
    corpus_root,
    ensure_parent,
    pending_judgement_path,
)


def _load_candles_from_ohlc_file(path: Path) -> list[Candle]:
    """Load candles from a JSONL or JSON-array OHLC file."""
    text = path.read_text(encoding="utf-8")
    records: list[dict]
    if text.strip().startswith("["):
        records = json.loads(text)
    else:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    return load_ohlc_records(records)


def prepare_check(
    *,
    symbol: str,
    timeframe: str,
    candles: list[Candle],
    corpus_name: str = "default",
    top_k: int = 10,
    window_size: int = 60,
    asof_utc: datetime | None = None,
) -> dict:
    """Build pack + prompt and persist them. Returns metadata for the caller."""
    if len(candles) < window_size:
        raise ValueError(
            f"need at least {window_size} candles, got {len(candles)}"
        )
    window = candles[-window_size:]
    asof = asof_utc or window[-1].t
    atr_m5 = atr(window, period=14)
    pivots = detect_multi_scale_pivots(window, atr_m5=atr_m5)
    pack = build_market_pack_v2(
        symbol=symbol,
        asof_utc=asof,
        candles=window,
        pivots=pivots,
        atr_m5_14=atr_m5,
        high_24h=max(c.h for c in window),
        low_24h=min(c.l for c in window),
        current_price=window[-1].c,
    )
    vector = chart_pack_to_vector(pack)

    store = JsonlVectorStore(corpus_root(corpus_name))
    retrieved = store.search_similar(
        vector,
        top_k=top_k,
        recency_weight=0.5,
        now_utc=asof,
    )

    prompt = build_decision_prompt(pack, retrieved=retrieved)

    entry_id = str(uuid.uuid4())
    pending_path = pending_judgement_path(entry_id)
    ensure_parent(pending_path)
    payload = {
        "schema_version": "pending_judgement_v1",
        "entry_id": entry_id,
        "asof_utc": asof.isoformat(),
        "symbol": symbol,
        "timeframe": timeframe,
        "corpus_name": corpus_name,
        "market_pack": pack.model_dump(mode="json"),
        "feature_vector": vector.tolist(),
        "retrieved_entry_ids": [e.entry_id for _, e in retrieved],
        "knowledge_pack_path": prompt.knowledge_pack_path,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    pending_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    prompt_md_path = pending_path.with_suffix(".prompt.md")
    prompt_md = (
        f"# /royal-road-check prompt for entry {entry_id}\n\n"
        f"## SYSTEM\n\n```\n{prompt.system}\n```\n\n"
        f"## USER\n\n{prompt.user}\n"
    )
    prompt_md_path.write_text(prompt_md, encoding="utf-8")

    return {
        "entry_id": entry_id,
        "pending_path": str(pending_path),
        "prompt_path": str(prompt_md_path),
        "retrieved_count": len(retrieved),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fx_monitor.tools.check_prepare")
    p.add_argument("--symbol", default="EURUSD=X")
    p.add_argument("--timeframe", default="M5")
    p.add_argument(
        "--ohlc-file",
        required=True,
        type=Path,
        help="Path to a JSON / JSONL file with candle records (t/o/h/l/c/v).",
    )
    p.add_argument("--corpus-name", default="default")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--window-size", type=int, default=60)
    args = p.parse_args(argv)

    candles = _load_candles_from_ohlc_file(args.ohlc_file)
    info = prepare_check(
        symbol=args.symbol,
        timeframe=args.timeframe,
        candles=candles,
        corpus_name=args.corpus_name,
        top_k=args.top_k,
        window_size=args.window_size,
    )
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
