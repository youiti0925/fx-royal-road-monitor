"""CLI: render the offline draft-review dashboard.

Usage:

    python -m fx_monitor.app.dashboard \\
        --diagnostics out/diagnostics.json \\
        --summary out/review_report.json \\
        --html out/dashboard.html

Offline analysis only.
"""

from __future__ import annotations

import argparse

from ..logging.dashboard import write_dashboard


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fx_monitor.app.dashboard",
        description="Render the offline draft-review HTML dashboard.",
    )
    parser.add_argument("--diagnostics", default="out/diagnostics.json")
    parser.add_argument("--summary", default="out/review_report.json")
    parser.add_argument("--html", default="out/dashboard.html")
    args = parser.parse_args(argv)

    path = write_dashboard(
        diagnostics_path=args.diagnostics,
        review_summary_path=args.summary,
        html_path=args.html,
    )

    print(f"Dashboard: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
