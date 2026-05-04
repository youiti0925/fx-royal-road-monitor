"""Build a one-click HTML preview of the MVP-1 observation pipeline.

Renders into ``docs/mvp1_current_preview/`` so the directory can be served
by https://htmlpreview.github.io directly off ``main`` — no Actions tab,
no zip download, no ``unzip``. The preview is generated from a safe CSV
fixture, so it is observation-only by construction.

Usage:

    python -m fx_monitor.app.build_preview \\
        --out-dir docs/mvp1_current_preview

Pipeline:

    1. Run ``fx_monitor.app.run_once`` against the preview CSV fixture
       with safe env (DRY_RUN, all reviewers disabled, dispatch off).
    2. Generate ``review_report.md`` / ``review_report.json``.
    3. Generate ``dashboard.html``.
    4. Copy the six artifact files into ``out-dir``.
    5. Render an ``index.html`` with the safety banner, the embedded
       chart, and links to dashboard / diagnostics / review report.

Never produces READY. Never dispatches notifications. Never trades.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CSV = REPO_ROOT / "tests" / "fixtures" / "ohlc_preview_sample.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "docs" / "mvp1_current_preview"
DEFAULT_WORK_DIR = REPO_ROOT / "out"

ARTIFACT_FILES = (
    "dashboard.html",
    "draft_chart.png",
    "diagnostics.json",
    "review_report.md",
    "review_report.json",
    "review_log.jsonl",
)


def _safe_env(csv_path: Path, work: Path) -> dict[str, str]:
    env = {
        **os.environ,
        "DRY_RUN": "true",
        "AI_USE_MOCK": "false",
        "OPENAI_ENABLED": "false",
        "ANTHROPIC_ENABLED": "false",
        "FX_MONITOR_FEED": "csv",
        "FX_MONITOR_CSV_PATH": str(csv_path),
        "FX_MONITOR_SYMBOL": "EURUSD=X",
        "FX_MONITOR_TIMEFRAME": "M5",
        "FX_MONITOR_REVIEW_DRAFT_WITH_AI": "true",
        "FX_MONITOR_REVIEW_LOG_PATH": str(work / "review_log.jsonl"),
        "FX_MONITOR_DIAGNOSTICS_PATH": str(work / "diagnostics.json"),
        "FX_MONITOR_RENDER_DRAFT_CHART": "true",
        "FX_MONITOR_DRAFT_CHART_PATH": str(work / "draft_chart.png"),
        # Ensure no fixture path leaks in.
    }
    env.pop("FX_MONITOR_FIXTURE_PATH", None)
    # Strip any real API keys so the preview is reproducible.
    env.pop("OPENAI_API_KEY", None)
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def _run(cmd: list[str], env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, check=True, env=env)


def _esc(value: object) -> str:
    return html.escape(str(value))


def _safety_status(diagnostics: dict, review_summary: dict) -> tuple[bool, dict]:
    decision = diagnostics.get("decision") or {}
    safety = diagnostics.get("safety") or {}
    rich = (diagnostics.get("draft") or {}).get("rich_draft") or {}
    summary_safety = review_summary.get("safety") or {}

    flags = {
        "decision.level": decision.get("level"),
        "safety.ready_allowed": safety.get("ready_allowed"),
        "safety.dispatch_called": safety.get("dispatch_called"),
        "rich_draft.ready_eligible": rich.get("ready_eligible"),
        "rich_draft.p0_pass": rich.get("p0_pass"),
        "summary.used_for_ready": summary_safety.get("used_for_ready"),
        "summary.used_for_notification": summary_safety.get("used_for_notification"),
        "summary.offline_analysis_only": summary_safety.get("offline_analysis_only"),
    }

    ok = (
        decision.get("level") == "SUPPRESSED"
        and safety.get("ready_allowed") is False
        and safety.get("dispatch_called") is False
        and (rich.get("ready_eligible") in (False, None))
        and (rich.get("p0_pass") in (False, None))
        and summary_safety.get("used_for_ready") is False
        and summary_safety.get("used_for_notification") is False
    )
    return ok, flags


def _render_index_html(out_dir: Path) -> str:
    diag = json.loads((out_dir / "diagnostics.json").read_text(encoding="utf-8"))
    summary = json.loads((out_dir / "review_report.json").read_text(encoding="utf-8"))

    safe, flags = _safety_status(diag, summary)
    banner_class = "safe" if safe else "bad"
    banner_text = (
        "SAFE: offline analysis only — NOT READY ELIGIBLE"
        if safe
        else "CHECK SAFETY FLAGS"
    )

    feed = diag.get("feed") or {}
    draft = diag.get("draft") or {}
    rich = draft.get("rich_draft") or {}

    flag_rows = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in flags.items()
    )

    summary_rows = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>"
        for k, v in (
            ("symbol", feed.get("symbol")),
            ("timeframe", feed.get("timeframe")),
            ("source", feed.get("source")),
            ("candles", feed.get("candles")),
            ("last_close", feed.get("last_close")),
            ("rich_draft.pattern_kind", rich.get("pattern_kind")),
            ("rich_draft.wave_lines", rich.get("wave_lines")),
            ("rich_draft.structural_lines", rich.get("structural_lines")),
            ("rich_draft.sr_zones", rich.get("sr_zones")),
            ("rich_draft.trendlines", rich.get("trendlines")),
            ("rich_draft.ready_eligible", rich.get("ready_eligible")),
        )
    )

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>MVP-1 Observation Pipeline Preview</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Noto Sans CJK JP",
        "Yu Gothic", "Meiryo", sans-serif;
      background: #f4f7fb;
      color: #172033;
    }}
    header {{
      padding: 22px 28px;
      background: #0f172a;
      color: white;
    }}
    h1 {{ margin: 0; font-size: 24px; }}
    .sub {{ color: #cbd5e1; margin-top: 6px; font-size: 13px; }}
    main {{ padding: 24px; max-width: 1100px; margin: 0 auto; }}
    .banner {{
      padding: 16px 18px;
      border-radius: 14px;
      margin-bottom: 18px;
      font-weight: 700;
      font-size: 15px;
    }}
    .banner.safe {{ background: #dcfce7; color: #166534; }}
    .banner.bad  {{ background: #fee2e2; color: #991b1b; }}
    section {{
      background: white;
      border: 1px solid #dbe4f0;
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 18px;
      box-shadow: 0 6px 20px rgba(15, 23, 42, .05);
    }}
    h2 {{ font-size: 16px; margin: 0 0 10px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{
      border-bottom: 1px solid #e5eaf2;
      padding: 7px 6px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ color: #475569; width: 38%; font-weight: 600; }}
    img.chart {{
      width: 100%;
      border-radius: 10px;
      border: 1px solid #dbe4f0;
      background: white;
    }}
    .links a {{
      display: inline-block;
      margin-right: 12px;
      padding: 8px 12px;
      border-radius: 8px;
      background: #e2e8f0;
      color: #1e293b;
      text-decoration: none;
      font-size: 13px;
      font-weight: 600;
    }}
    .links a:hover {{ background: #cbd5e1; }}
    footer {{
      color: #64748b;
      font-size: 12px;
      padding: 24px;
      text-align: center;
    }}
    .muted {{ color: #64748b; font-size: 12px; }}
  </style>
</head>
<body>
  <header>
    <h1>MVP-1 Observation Pipeline Preview</h1>
    <div class="sub">
      offline preview / generated from a safe CSV fixture /
      not used for READY / not used for notifications / not used for trading
    </div>
  </header>
  <main>
    <div class="banner {banner_class}">{_esc(banner_text)}</div>

    <section>
      <h2>Draft chart</h2>
      <img class="chart" src="./draft_chart.png" alt="Draft rich chart (observation only)">
      <p class="muted">
        Image carries an "OBSERVATION ONLY / NOT READY ELIGIBLE / source=draft /
        ready_eligible=False" banner. Lines: P1/NL/P2/BR (or B1/NL/B2/BR),
        WNL_D1/WSL_D1/WTP_D1, SNL_D1/SIL_D1/STP_D1/STL_D1.
      </p>
    </section>

    <section>
      <h2>Safety flags</h2>
      <table>{flag_rows}</table>
    </section>

    <section>
      <h2>Snapshot summary</h2>
      <table>{summary_rows}</table>
    </section>

    <section class="links">
      <h2>More detail</h2>
      <a href="./dashboard.html">Open full dashboard.html</a>
      <a href="./diagnostics.json">diagnostics.json</a>
      <a href="./review_report.md">review_report.md</a>
      <a href="./review_report.json">review_report.json</a>
      <a href="./review_log.jsonl">review_log.jsonl</a>
    </section>
  </main>
  <footer>
    Generated by <code>python -m fx_monitor.app.build_preview</code>
    from <code>tests/fixtures/ohlc_preview_sample.csv</code>.
    Never used for READY / notification / trading / order execution.
  </footer>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fx_monitor.app.build_preview",
        description="Build the MVP-1 observation pipeline HTML preview.",
    )
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
    args = parser.parse_args(argv)

    csv_path = Path(args.csv).resolve()
    out_dir = Path(args.out_dir).resolve()
    work_dir = Path(args.work_dir).resolve()

    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Clean stale outputs in the working directory so we know what we built.
    for name in ARTIFACT_FILES:
        p = work_dir / name
        if p.exists():
            p.unlink()

    env = _safe_env(csv_path, work_dir)

    _run([sys.executable, "-m", "fx_monitor.app.run_once"], env=env)
    _run(
        [
            sys.executable,
            "-m",
            "fx_monitor.app.review_report",
            "--log",
            str(work_dir / "review_log.jsonl"),
            "--md",
            str(work_dir / "review_report.md"),
            "--json",
            str(work_dir / "review_report.json"),
        ]
    )
    _run(
        [
            sys.executable,
            "-m",
            "fx_monitor.app.dashboard",
            "--diagnostics",
            str(work_dir / "diagnostics.json"),
            "--summary",
            str(work_dir / "review_report.json"),
            "--html",
            str(work_dir / "dashboard.html"),
        ]
    )

    for name in ARTIFACT_FILES:
        src = work_dir / name
        if src.exists():
            shutil.copy2(src, out_dir / name)

    index_html = _render_index_html(out_dir)
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")

    print(f"Preview written to: {out_dir}")
    print(f"  index.html        : {(out_dir / 'index.html').stat().st_size} B")
    print(f"  dashboard.html    : {(out_dir / 'dashboard.html').stat().st_size} B")
    print(f"  draft_chart.png   : {(out_dir / 'draft_chart.png').stat().st_size} B")
    print(f"  diagnostics.json  : {(out_dir / 'diagnostics.json').stat().st_size} B")
    print(f"  review_report.md  : {(out_dir / 'review_report.md').stat().st_size} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
