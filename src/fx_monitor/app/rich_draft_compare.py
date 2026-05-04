"""CLI: compare a draft rich payload to a reference royal-road payload.

Usage:

    python -m fx_monitor.app.rich_draft_compare \\
        --draft tests/fixtures/sample_rich_draft.json \\
        --reference tests/fixtures/sample_reference_payload.json \\
        --out out/rich_draft_compare.json

Offline analysis only — never used for READY decisions, notifications,
or trading.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..analysis.rich_draft_compare import compare_rich_draft_to_reference


def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fx_monitor.app.rich_draft_compare",
        description="Compare a draft rich payload to a reference (offline only).",
    )
    parser.add_argument("--draft", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--out", default="out/rich_draft_compare.json")
    args = parser.parse_args(argv)

    draft = _load(args.draft)
    reference = _load(args.reference)
    result = compare_rich_draft_to_reference(draft=draft, reference=reference)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    scores = result["scores"]
    print(
        "Rich draft compare: "
        f"pattern={scores['pattern_match']:.2f} "
        f"wave={scores['wave_line_presence']:.2f} "
        f"structural={scores['structural_line_presence']:.2f} "
        f"sr={scores['sr_presence']:.2f} "
        f"trendline={scores['trendline_presence']:.2f}"
    )
    print(f"Compare report: {out_path}")
    print(
        "Safety: offline_analysis_only=True / used_for_ready=False / "
        "used_for_notification=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
