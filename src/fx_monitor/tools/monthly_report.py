"""Monthly self-diagnosis report over the corpus.

Aggregates: judgement counts by final_status, outcome distribution,
WIN/LOSE rate among scored entries, dissent flag counts, retrieval
sanity (placeholder until we wire it into live).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

from fx_monitor.corpus.store import JsonlVectorStore

from ._paths import corpus_root


def build_report(
    *,
    corpus_name: str = "default",
    days: int = 30,
    now_utc: datetime | None = None,
) -> dict:
    now = now_utc or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    store = JsonlVectorStore(corpus_root(corpus_name))

    recent = []
    for e in store.all():
        asof = e.asof_utc
        if asof.tzinfo is None:
            asof = asof.replace(tzinfo=timezone.utc)
        if asof >= cutoff:
            recent.append(e)

    final_status = Counter(e.judgement.final_status for e in recent)
    side = Counter(e.judgement.side for e in recent)
    outcome = Counter(e.outcome.status for e in recent)

    scored = [e for e in recent if e.outcome.status in ("WIN", "LOSE")]
    if scored:
        wins = sum(1 for e in scored if e.outcome.status == "WIN")
        win_rate = wins / len(scored)
    else:
        win_rate = None

    dissent = sum(1 for e in recent if e.user_dissent)

    return {
        "schema_version": "monthly_report_v1",
        "corpus_name": corpus_name,
        "window_days": days,
        "generated_at_utc": now.isoformat(),
        "total_entries_in_window": len(recent),
        "total_corpus_size": len(store),
        "final_status_counts": dict(final_status),
        "side_counts": dict(side),
        "outcome_counts": dict(outcome),
        "win_rate_among_scored": win_rate,
        "dissent_count": dissent,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fx_monitor.tools.monthly_report")
    p.add_argument("--corpus-name", default="default")
    p.add_argument("--days", type=int, default=30)
    args = p.parse_args(argv)

    report = build_report(corpus_name=args.corpus_name, days=args.days)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
