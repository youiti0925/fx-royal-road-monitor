"""Build the Japanese-UI MVP-1 royal-road decision preview.

Pipeline (every output observation-only, no READY, no dispatch):

  1. Run feed mode against the populated CSV fixture.
     -> review_log.jsonl, diagnostics.json, draft_chart.png
  2. Generate review_report.md / review_report.json.
  3. Generate dashboard.html and post-process to Japanese headings.
  4. Build the royal-road decision screen (HTML inline-SVG + PNG).
  5. Run AI visual review against the decision screen PNG. The visual
     review never feeds READY / notification / trading; if API keys
     are absent (the default), each provider returns UNKNOWN.
  6. Scrub absolute filesystem paths from the JSON / JSONL outputs so
     committed artifacts do not leak the build host's directory.
  7. Render index.html in Japanese with the decision screen inline.

Open the result via:
  https://htmlpreview.github.io/?https://raw.githubusercontent.com/
  youiti0925/fx-royal-road-monitor/main/docs/mvp1_current_preview/index.html
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
from typing import Any

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


def _safe_env(csv_rel: str, work_rel: str) -> dict[str, str]:
    env = {
        **os.environ,
        "DRY_RUN": "true",
        "AI_USE_MOCK": "false",
        "OPENAI_ENABLED": "false",
        "ANTHROPIC_ENABLED": "false",
        "FX_MONITOR_FEED": "csv",
        "FX_MONITOR_CSV_PATH": csv_rel,
        "FX_MONITOR_SYMBOL": "EURUSD=X",
        "FX_MONITOR_TIMEFRAME": "M5",
        "FX_MONITOR_REVIEW_DRAFT_WITH_AI": "true",
        "FX_MONITOR_REVIEW_LOG_PATH": f"{work_rel}/review_log.jsonl",
        "FX_MONITOR_DIAGNOSTICS_PATH": f"{work_rel}/diagnostics.json",
        "FX_MONITOR_RENDER_DRAFT_CHART": "true",
        "FX_MONITOR_DRAFT_CHART_PATH": f"{work_rel}/draft_chart.png",
    }
    env.pop("FX_MONITOR_FIXTURE_PATH", None)
    # Reproducible committed preview: do not call live APIs.
    env.pop("OPENAI_API_KEY", None)
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def _run(cmd: list[str], env: dict[str, str] | None = None, cwd: Path | None = None) -> None:
    subprocess.run(cmd, check=True, env=env, cwd=cwd)


def _scrub_paths(text: str) -> str:
    repo = str(REPO_ROOT)
    return text.replace(repo + "/", "").replace(repo, "")


def _scrub_file(path: Path) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    path.write_text(_scrub_paths(text), encoding="utf-8")


_DASHBOARD_JA_RENAMES = (
    ("FX Monitor Draft Review Dashboard", "MVP-1 王道判定ダッシュボード"),
    (
        "offline artifact / not used for READY / not used for notification",
        "観測専用 / READY通知不可 / 売買未使用",
    ),
    ("SAFE: offline analysis only", "安全: 観測専用"),
    ("CHECK SAFETY FLAGS", "安全フラグ要確認"),
    (">Feed<", ">データ取得<"),
    (">Draft<", ">下書き分析<"),
    (">Rich draft<", ">王道構造下書き<"),
    (">Decision<", ">判定<"),
    (">Rule<", ">ルール判定<"),
    (">OpenAI<", ">OpenAIレビュー<"),
    (">Claude<", ">Claudeレビュー<"),
    (">Compare<", ">AI比較<"),
    (">Review summary<", ">レビュー集計<"),
    (">Safety flags<", ">安全フラグ<"),
    (">Top OpenAI missing<", ">OpenAI 不足項目<"),
    (">Top Claude missing<", ">Claude 不足項目<"),
    (">Top OpenAI disagreements<", ">OpenAI 不一致<"),
    (">Top Claude disagreements<", ">Claude 不一致<"),
    (">Top OpenAI reasons<", ">OpenAI 主要理由<"),
    (">Top Claude reasons<", ">Claude 主要理由<"),
    ("Open draft chart", "下書きチャートを開く"),
    (
        "This dashboard is generated from diagnostics.json and review_report.json.",
        "本画面は diagnostics.json と review_report.json から生成しています。",
    ),
    (
        "It is never used for trading, READY decisions, or notifications.",
        "売買 / READY判定 / 通知には使いません。",
    ),
)


def _localize_dashboard_html(path: Path) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    for src, dst in _DASHBOARD_JA_RENAMES:
        text = text.replace(src, dst)
    text = _scrub_paths(text)
    path.write_text(text, encoding="utf-8")


def _run_visual_review(decision_png: Path, context_summary: str) -> dict[str, Any]:
    from ..ai.claude_reviewer import ClaudeReviewer
    from ..ai.openai_reviewer import OpenAIReviewer

    image_bytes = decision_png.read_bytes() if decision_png.exists() else b""

    openai_review = OpenAIReviewer().visual_review(
        image_bytes=image_bytes, context_summary=context_summary
    )
    claude_review = ClaudeReviewer().visual_review(
        image_bytes=image_bytes, context_summary=context_summary
    )

    def _to_summary(r: Any) -> dict[str, Any]:
        return {
            "verdict": r.verdict,
            "readability": r.readability,
            "language": r.language,
            "royal_road_clarity": r.royal_road_clarity,
            "line_visibility": r.line_visibility,
            "safety_clarity": r.safety_clarity,
            "problems": list(r.problems[:5]),
            "summary_ja": r.summary_ja,
        }

    combined = "UNKNOWN"
    if openai_review.verdict == "PASS" and claude_review.verdict == "PASS":
        combined = "PASS"
    elif "FAIL" in (openai_review.verdict, claude_review.verdict):
        combined = "FAIL"
    elif "WARN" in (openai_review.verdict, claude_review.verdict):
        combined = "WARN"

    return {
        "schema_version": "visual_review_v1",
        "providers": {
            "openai": _to_summary(openai_review),
            "claude": _to_summary(claude_review),
        },
        "combined_verdict": combined,
        "used_for_ready": False,
        "used_for_notification": False,
        "used_for_trading": False,
        "context_summary": context_summary,
    }


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _render_index_html(out_dir: Path, visual_review: dict[str, Any]) -> str:
    diag = json.loads((out_dir / "diagnostics.json").read_text(encoding="utf-8"))
    summary = json.loads((out_dir / "review_report.json").read_text(encoding="utf-8"))

    decision = diag.get("decision") or {}
    safety = diag.get("safety") or {}
    feed = diag.get("feed") or {}
    rich = (diag.get("draft") or {}).get("rich_draft") or {}
    summary_safety = summary.get("safety") or {}

    safe = (
        decision.get("level") == "SUPPRESSED"
        and safety.get("ready_allowed") is False
        and safety.get("dispatch_called") is False
        and rich.get("ready_eligible") is False
        and rich.get("p0_pass") is False
        and summary_safety.get("used_for_ready") is False
        and summary_safety.get("used_for_notification") is False
    )
    banner_class = "ok" if safe else "bad"
    banner_text = (
        "安全: 観測専用 / READY通知不可 / 売買未使用"
        if safe
        else "安全フラグ要確認 / CHECK SAFETY FLAGS"
    )

    visual_rows = []
    for name, label in (("openai", "OpenAI"), ("claude", "Claude")):
        r = (visual_review.get("providers") or {}).get(name) or {}
        visual_rows.append(
            "<tr>"
            f"<th>{_esc(label)}</th>"
            f"<td>判定: <b>{_esc(r.get('verdict', 'UNKNOWN'))}</b><br>"
            f"日本語UI: {_esc(r.get('language', 'UNKNOWN'))}<br>"
            f"線の見やすさ: {_esc(r.get('line_visibility', 'UNKNOWN'))}<br>"
            f"安全性表記: {_esc(r.get('safety_clarity', 'UNKNOWN'))}<br>"
            f"<span class='muted'>{_esc(r.get('summary_ja', ''))}</span></td>"
            "</tr>"
        )
    combined_v = visual_review.get("combined_verdict") or "UNKNOWN"

    flags_rows = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>"
        for k, v in (
            ("判定", decision.get("level")),
            ("READY許可", safety.get("ready_allowed")),
            ("通知実行", safety.get("dispatch_called")),
            ("rich_draft.ready_eligible", rich.get("ready_eligible")),
            ("rich_draft.p0_pass", rich.get("p0_pass")),
            ("REVIEW.used_for_ready", summary_safety.get("used_for_ready")),
            ("REVIEW.used_for_notification", summary_safety.get("used_for_notification")),
            ("REVIEW.offline_analysis_only", summary_safety.get("offline_analysis_only")),
        )
    )

    feed_rows = "".join(
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
        )
    )

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>MVP-1 王道判定プレビュー</title>
  <style>
    body {{ margin:0; font-family: -apple-system, BlinkMacSystemFont,
       "Noto Sans CJK JP", "Yu Gothic", "Meiryo", sans-serif;
       background:#f4f7fb; color:#172033; }}
    header {{ padding:22px 28px; background:#0f172a; color:white; }}
    h1 {{ margin:0; font-size:22px; }}
    .sub {{ color:#cbd5e1; margin-top:6px; font-size:13px; }}
    main {{ padding:24px; max-width:1200px; margin:0 auto; }}
    .banner {{ padding:16px 18px; border-radius:14px; margin-bottom:18px;
       font-weight:700; font-size:15px; }}
    .banner.ok {{ background:#dcfce7; color:#166534; }}
    .banner.bad {{ background:#fee2e2; color:#991b1b; }}
    section {{ background:white; border:1px solid #dbe4f0;
       border-radius:14px; padding:18px; margin-bottom:18px;
       box-shadow:0 6px 20px rgba(15,23,42,.05); }}
    h2 {{ font-size:16px; margin:0 0 10px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-bottom:1px solid #e5eaf2; padding:7px 6px;
       text-align:left; vertical-align:top; }}
    th {{ color:#475569; width:38%; font-weight:600; }}
    img.screen {{ width:100%; border-radius:10px; border:1px solid #dbe4f0;
       background:white; }}
    .links a {{ display:inline-block; margin-right:12px; padding:8px 12px;
       border-radius:8px; background:#e2e8f0; color:#1e293b;
       text-decoration:none; font-size:13px; font-weight:600; }}
    .links a:hover {{ background:#cbd5e1; }}
    .muted {{ color:#64748b; font-size:12px; }}
    footer {{ color:#64748b; font-size:12px; padding:24px; text-align:center; }}
  </style>
</head>
<body>
  <header>
    <h1>MVP-1 王道判定プレビュー</h1>
    <div class="sub">
      観測専用 / READY通知不可 / 売買未使用 /
      OANDA・live・paper未接続 / 取引執行未使用
    </div>
  </header>
  <main>
    <div class="banner {banner_class}">{_esc(banner_text)}</div>

    <section>
      <h2>王道判定画面 (decision_screen)</h2>
      <img class="screen" src="./decision_screen.png"
           alt="王道判定画面 (観測専用)">
      <p class="muted">
        画面内に「観測専用 / NOT READY ELIGIBLE」を明記。
        ENTRY指示ではありません。本番READY判定には未使用。
      </p>
      <p class="links" style="margin-top:8px">
        <a href="./decision_screen.html">王道判定画面HTMLを開く</a>
        <a href="./dashboard.html">詳細ダッシュボードを開く</a>
      </p>
    </section>

    <section>
      <h2>AI画面レビュー (画面の見やすさのみ。売買判定ではありません)</h2>
      <table>{"".join(visual_rows)}
        <tr><th>総合判定</th><td><b>{_esc(combined_v)}</b></td></tr>
      </table>
    </section>

    <section>
      <h2>安全フラグ</h2>
      <table>{flags_rows}</table>
    </section>

    <section>
      <h2>下書き要約</h2>
      <table>{feed_rows}</table>
    </section>

    <section class="links">
      <h2>追加データ</h2>
      <a href="./diagnostics.json">診断JSON</a>
      <a href="./review_report.md">AIレビュー集計 (md)</a>
      <a href="./review_report.json">AIレビュー集計 (json)</a>
      <a href="./visual_review.json">画面レビュー詳細 (json)</a>
      <a href="./review_log.jsonl">レビュー生ログ</a>
      <a href="./draft_chart.png">下書きチャート (旧形式)</a>
    </section>
  </main>
  <footer>
    生成: <code>python -m fx_monitor.app.build_preview</code> /
    入力: <code>tests/fixtures/ohlc_preview_sample.csv</code> /
    READY通知 / 通知 / 売買・取引執行 には使いません。
  </footer>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fx_monitor.app.build_preview",
        description="Build the MVP-1 royal-road decision preview (Japanese).",
    )
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
    args = parser.parse_args(argv)

    csv_path = Path(args.csv).resolve()
    out_dir = Path(args.out_dir).resolve()
    work_dir = Path(args.work_dir).resolve()

    csv_rel = str(csv_path.relative_to(REPO_ROOT))
    work_rel = str(work_dir.relative_to(REPO_ROOT))

    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    for name in ARTIFACT_FILES:
        p = work_dir / name
        if p.exists():
            p.unlink()

    env = _safe_env(csv_rel, work_rel)

    _run([sys.executable, "-m", "fx_monitor.app.run_once"], env=env, cwd=REPO_ROOT)
    _run(
        [
            sys.executable,
            "-m",
            "fx_monitor.app.review_report",
            "--log",
            f"{work_rel}/review_log.jsonl",
            "--md",
            f"{work_rel}/review_report.md",
            "--json",
            f"{work_rel}/review_report.json",
        ],
        cwd=REPO_ROOT,
    )
    _run(
        [
            sys.executable,
            "-m",
            "fx_monitor.app.dashboard",
            "--diagnostics",
            f"{work_rel}/diagnostics.json",
            "--summary",
            f"{work_rel}/review_report.json",
            "--html",
            f"{work_rel}/dashboard.html",
        ],
        cwd=REPO_ROOT,
    )

    for name in ARTIFACT_FILES:
        src = work_dir / name
        if src.exists():
            shutil.copy2(src, out_dir / name)

    from ..analysis import build_royal_road_draft_payload_from_snapshot
    from ..data.csv_feed import load_ohlc_csv
    from ..render.royal_road_decision_screen import (
        build_royal_road_decision_screen_html,
        render_royal_road_decision_screen_png,
    )

    diag = json.loads((out_dir / "diagnostics.json").read_text(encoding="utf-8"))
    summary = json.loads((out_dir / "review_report.json").read_text(encoding="utf-8"))

    snap = load_ohlc_csv(csv_path, symbol="EURUSD=X", timeframe="M5")
    full_draft = build_royal_road_draft_payload_from_snapshot(snap)
    full_rich_draft = full_draft.rich_draft or {}

    decision_png = out_dir / "decision_screen.png"
    render_royal_road_decision_screen_png(
        rich_draft=full_rich_draft,
        diagnostics=diag,
        out_path=decision_png,
    )

    feed = diag.get("feed") or {}
    rich = (diag.get("draft") or {}).get("rich_draft") or {}
    context = (
        f"symbol={feed.get('symbol')} timeframe={feed.get('timeframe')} "
        f"pattern={rich.get('pattern_kind')}"
    )
    visual_review = _run_visual_review(decision_png, context_summary=context)
    (out_dir / "visual_review.json").write_text(
        json.dumps(visual_review, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    decision_html = build_royal_road_decision_screen_html(
        rich_draft=full_rich_draft,
        diagnostics=diag,
        review_summary=summary,
        visual_review=visual_review,
    )
    (out_dir / "decision_screen.html").write_text(decision_html, encoding="utf-8")

    _localize_dashboard_html(out_dir / "dashboard.html")

    for name in (
        "diagnostics.json",
        "review_log.jsonl",
        "review_report.md",
        "review_report.json",
        "visual_review.json",
    ):
        _scrub_file(out_dir / name)

    index_html = _render_index_html(out_dir, visual_review)
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")

    files = [
        "index.html",
        "decision_screen.html",
        "decision_screen.png",
        "dashboard.html",
        "draft_chart.png",
        "diagnostics.json",
        "review_report.md",
        "review_report.json",
        "review_log.jsonl",
        "visual_review.json",
    ]
    print(f"Preview written to: {out_dir}")
    for name in files:
        p = out_dir / name
        size = p.stat().st_size if p.exists() else 0
        print(f"  {name:<22}: {size} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
