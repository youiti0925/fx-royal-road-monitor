"""CLI: summarize the draft AI review JSONL log into Markdown + JSON.

Usage:

    python -m fx_monitor.app.review_report \\
        --log out/review_log.jsonl \\
        --md out/review_report.md \\
        --json out/review_report.json

Offline analysis only — does not influence READY, notifications, or any
trading path.
"""

from __future__ import annotations

import argparse

from ..logging.review_report import write_review_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fx_monitor.app.review_report",
        description="Summarize the draft AI review JSONL log.",
    )
    parser.add_argument("--log", default="out/review_log.jsonl")
    parser.add_argument("--md", default="out/review_report.md")
    parser.add_argument("--json", default="out/review_report.json")
    args = parser.parse_args(argv)

    summary = write_review_report(
        log_path=args.log,
        markdown_path=args.md,
        json_path=args.json,
    )

    print(f"Review records: {summary['total_records']}")
    print(f"Markdown report: {args.md}")
    print(f"JSON summary: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
