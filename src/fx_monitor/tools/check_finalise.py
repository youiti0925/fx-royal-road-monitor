"""Finalise a ``/royal-road-check`` after Claude Code returns the spec.

Reads the pending judgement file written by ``check_prepare``, parses
the AI-generated spec JSON, runs Layer 3 post-validation, downgrades
to UNKNOWN on validation errors, and stores the entry in the corpus.
The pending file is removed on success.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from fx_monitor.ai.decision_screen_spec_schema import (
    AiDecisionScreenSpec,
    parse_decision_screen_spec,
)
from fx_monitor.corpus.schema import CorpusEntry, OutcomeLabel
from fx_monitor.corpus.store import JsonlVectorStore
from fx_monitor.live.market_pack_v2 import MarketAnalysisPackV2
from fx_monitor.live.post_validate import post_validate

from ._paths import corpus_root, pending_judgement_path


def finalise_check(
    *,
    entry_id: str,
    spec_json: str | dict,
    judgement_model: str = "claude-code-via-subscription",
    corpus_name: str = "default",
    skip_corpus_validation: bool = False,
) -> dict:
    """Finalise a pending judgement.

    ``skip_corpus_validation`` (default False) bypasses the strict
    :func:`entry_validator.validate_entry` check inside the corpus store.
    Production callers must leave this False — a True value is intended only
    for integration smoke tests that construct minimal stub specs.
    """
    pending = pending_judgement_path(entry_id)
    if not pending.exists():
        raise FileNotFoundError(f"no pending judgement for entry_id={entry_id}")
    payload = json.loads(pending.read_text(encoding="utf-8"))
    pack = MarketAnalysisPackV2.model_validate(payload["market_pack"])

    spec = parse_decision_screen_spec(
        provider="claude",
        payload=spec_json,
        symbol=payload["symbol"],
        timeframe=payload["timeframe"],
    )
    validation = post_validate(spec, pack)
    if validation.downgraded:
        spec = spec.model_copy(update={"final_status": "UNKNOWN"})

    entry = CorpusEntry(
        entry_id=entry_id,
        asof_utc=datetime.fromisoformat(payload["asof_utc"]),
        symbol=payload["symbol"],
        timeframe=payload["timeframe"],
        source="live_recorded",
        market_pack=pack,
        feature_vector=payload["feature_vector"],
        clip_vector=payload.get("clip_vector"),
        judgement=spec,
        judgement_model=judgement_model,
        judgement_at_utc=datetime.now(timezone.utc),
        outcome=OutcomeLabel(status="PENDING"),
    )
    store = JsonlVectorStore(corpus_root(corpus_name))
    store.add(entry, skip_validation=skip_corpus_validation)

    # Best-effort cleanup: keep the prompt for audit but drop the pending JSON.
    pending.unlink(missing_ok=True)

    return {
        "entry_id": entry_id,
        "final_status": spec.final_status,
        "side": spec.side,
        "validation_ok": validation.ok,
        "validation_issues": [i.model_dump() for i in validation.issues],
        "downgraded": validation.downgraded,
        "corpus_size": len(store),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fx_monitor.tools.check_finalise")
    p.add_argument("--id", dest="entry_id", required=True)
    p.add_argument(
        "--json",
        dest="spec_json",
        help="Inline JSON. Mutually exclusive with --json-file.",
    )
    p.add_argument(
        "--json-file",
        type=Path,
        help="Path to a file containing the spec JSON.",
    )
    p.add_argument("--corpus-name", default="default")
    args = p.parse_args(argv)

    if not args.spec_json and not args.json_file:
        p.error("one of --json or --json-file is required")
    spec_json = args.spec_json or args.json_file.read_text(encoding="utf-8")

    info = finalise_check(
        entry_id=args.entry_id,
        spec_json=spec_json,
        corpus_name=args.corpus_name,
    )
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
