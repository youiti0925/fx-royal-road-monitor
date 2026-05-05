"""Flag a corpus entry as user-dissent."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from fx_monitor.corpus.store import JsonlVectorStore

from ._paths import corpus_root


def flag_dissent(
    *,
    entry_id: str,
    note: str | None = None,
    corpus_name: str = "default",
) -> dict:
    store = JsonlVectorStore(corpus_root(corpus_name))
    ok = store.mark_dissent(
        entry_id, note=note, at_utc=datetime.now(timezone.utc)
    )
    return {"entry_id": entry_id, "ok": ok}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fx_monitor.tools.flag_dissent")
    p.add_argument("--id", dest="entry_id", required=True)
    p.add_argument("--note", default=None)
    p.add_argument("--corpus-name", default="default")
    args = p.parse_args(argv)

    info = flag_dissent(
        entry_id=args.entry_id,
        note=args.note,
        corpus_name=args.corpus_name,
    )
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0 if info["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
