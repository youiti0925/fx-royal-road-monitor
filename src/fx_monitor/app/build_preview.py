"""Build the MVP-1 AI-authored royal-road decision preview.

Pipeline (every output observation-only — no READY, no dispatch):

  1. Run feed mode against the populated CSV fixture.
     -> review_log.jsonl, diagnostics.json, draft_chart.png
  2. Generate review_report.md / review_report.json.
  3. Generate dashboard.html and post-process to Japanese headings.
  4. Build a market_analysis_pack from snapshot + rich_draft +
     diagnostics + the royal-road knowledge pack.
  5. Ask OpenAI to author an AiDecisionScreenSpec.
  6. Ask Claude to author an AiDecisionScreenSpec.
  7. Compare the two specs.
  8. Render the AI-authored decision screen (HTML + PNG) — the
     renderer paints **only** what the specs say. No system-side
     line drawing.
  9. Scrub absolute filesystem paths from JSON / JSONL outputs.
 10. Render the Japanese index.html.

When API keys are absent (the default for the committed preview),
both specs come back as SAFE-UNKNOWN and the comparison is UNKNOWN.
The renderer renders an explicit "AI が画面を生成していない" state.

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


def _safe_env(csv_rel: str, work_rel: str, *, mode: str) -> dict[str, str]:
    """Build the env passed to the run_once subprocess.

    safe-local: API keys are stripped; reviewers self-disable.
    ai-authored: API keys (and OPENAI_ENABLED / ANTHROPIC_ENABLED)
                 flow through; build_preview's caller is responsible
                 for setting them.
    """
    env = {
        **os.environ,
        "DRY_RUN": "true",
        "AI_USE_MOCK": "false",
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

    if mode == "safe-local":
        # Strip secrets so the committed safe preview is reproducible
        # and never depends on which developer's keys happen to be set.
        env["OPENAI_ENABLED"] = "false"
        env["ANTHROPIC_ENABLED"] = "false"
        env.pop("OPENAI_API_KEY", None)
        env.pop("ANTHROPIC_API_KEY", None)
    else:
        # ai-authored: trust the caller's env. Default ENABLED to true
        # if the corresponding key is present so the operator does not
        # have to set both vars.
        if env.get("OPENAI_API_KEY") and not env.get("OPENAI_ENABLED"):
            env["OPENAI_ENABLED"] = "true"
        if env.get("ANTHROPIC_API_KEY") and not env.get("ANTHROPIC_ENABLED"):
            env["ANTHROPIC_ENABLED"] = "true"
    return env


def _validate_ai_authored_specs(
    openai_spec: dict,
    claude_spec: dict,
) -> list[str]:
    """Hard-fail conditions for ai-authored mode.

    Returns a list of error tags. Empty list = the AI specs are
    populated and safety-correct enough to publish as a user-facing
    preview.
    """
    errors: list[str] = []
    for name, spec in (("openai", openai_spec), ("claude", claude_spec)):
        if (spec.get("final_status") or "UNKNOWN") == "UNKNOWN":
            errors.append(f"{name}_spec_unknown")
        if not spec.get("points"):
            errors.append(f"{name}_points_empty")
        if not spec.get("lines"):
            errors.append(f"{name}_lines_empty")
        if not spec.get("procedure_steps"):
            errors.append(f"{name}_procedure_steps_empty")
        if spec.get("used_for_ready") is not False:
            errors.append(f"{name}_used_for_ready_not_false")
        if spec.get("used_for_notification") is not False:
            errors.append(f"{name}_used_for_notification_not_false")
        if spec.get("used_for_trading") is not False:
            errors.append(f"{name}_used_for_trading_not_false")
    return errors


def _ai_execution_state(
    openai_spec: dict,
    claude_spec: dict,
) -> dict[str, Any]:
    """Summarise per-provider execution state for the index page."""
    def _provider(spec: dict) -> dict[str, Any]:
        problems = list(spec.get("problems") or [])
        not_run_reason = ""
        for token in (
            "openai_disabled",
            "anthropic_disabled",
            "openai_api_key_missing",
            "anthropic_api_key_missing",
            "openai_sdk_import_failed",
            "anthropic_sdk_import_failed",
        ):
            if any(token in p for p in problems):
                not_run_reason = token
                break
        executed = (spec.get("final_status") or "UNKNOWN") != "UNKNOWN"
        return {
            "executed": executed,
            "final_status": spec.get("final_status") or "UNKNOWN",
            "not_run_reason": not_run_reason,
            "lines": len(spec.get("lines") or []),
            "points": len(spec.get("points") or []),
            "procedure_steps": len(spec.get("procedure_steps") or []),
            "problems": problems[:5],
        }

    return {
        "openai": _provider(openai_spec),
        "claude": _provider(claude_spec),
    }


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
        "売買・READY判定・通知 には使いません。",
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


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _render_index_html(
    out_dir: Path,
    openai_spec: dict[str, Any],
    claude_spec: dict[str, Any],
    comparison: dict[str, Any],
    *,
    mode: str,
    ai_state: dict[str, Any],
) -> str:
    diag = json.loads((out_dir / "diagnostics.json").read_text(encoding="utf-8"))
    summary = json.loads((out_dir / "review_report.json").read_text(encoding="utf-8"))

    decision = diag.get("decision") or {}
    safety = diag.get("safety") or {}
    feed = diag.get("feed") or {}
    summary_safety = summary.get("safety") or {}

    safe = (
        decision.get("level") == "SUPPRESSED"
        and safety.get("ready_allowed") is False
        and safety.get("dispatch_called") is False
        and summary_safety.get("used_for_ready") is False
        and summary_safety.get("used_for_notification") is False
        and openai_spec.get("used_for_ready") is False
        and openai_spec.get("used_for_notification") is False
        and openai_spec.get("used_for_trading") is False
        and claude_spec.get("used_for_ready") is False
        and claude_spec.get("used_for_notification") is False
        and claude_spec.get("used_for_trading") is False
    )
    banner_class = "ok" if safe else "bad"
    banner_text = (
        "安全: 観測専用 / READY通知不可 / 売買未使用"
        if safe
        else "安全フラグ要確認 / CHECK SAFETY FLAGS"
    )

    o_state = ai_state["openai"]
    c_state = ai_state["claude"]
    both_executed = o_state["executed"] and c_state["executed"]
    ai_state_class = "ok" if both_executed else "warn"
    ai_state_text = (
        "AI生成状態: 実行済み"
        if both_executed
        else (
            "AI生成状態: AI未実行 — 安全smoke用 / "
            "実際のAI生成王道判定画面ではありません"
        )
    )

    def _provider_status(name: str, s: dict[str, Any]) -> str:
        if s["executed"]:
            return (
                f"{name}: 実行済み (lines={s['lines']} / "
                f"points={s['points']} / steps={s['procedure_steps']} / "
                f"final_status={s['final_status']})"
            )
        reason = s["not_run_reason"] or "AI未実行"
        return f"{name}: 未実行 (理由: {reason})"

    ai_lines = "<br>".join(
        _esc(line)
        for line in (
            _provider_status("OpenAI", o_state),
            _provider_status("Claude", c_state),
            f"二者比較: {comparison.get('agreement', 'UNKNOWN')}",
            f"build_preview mode: {mode}",
        )
    )

    rows = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>"
        for k, v in (
            ("OpenAI画面設計", openai_spec.get("final_status")),
            ("Claude画面設計", claude_spec.get("final_status")),
            ("二者比較 (一致 / 不一致)", comparison.get("agreement")),
            ("symbol", feed.get("symbol")),
            ("timeframe", feed.get("timeframe")),
            ("decision.level", decision.get("level")),
            ("safety.ready_allowed", safety.get("ready_allowed")),
            ("safety.dispatch_called", safety.get("dispatch_called")),
        )
    )

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>MVP-1 AI生成 王道判定プレビュー</title>
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
    .banner.warn {{ background:#fef3c7; color:#92400e; }}
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
    .muted {{ color:#64748b; font-size:12px; }}
    footer {{ color:#64748b; font-size:12px; padding:24px; text-align:center; }}
  </style>
</head>
<body>
  <header>
    <h1>MVP-1 AI生成 王道判定プレビュー</h1>
    <div class="sub">
      観測専用 / READY通知不可 / 売買未使用 /
      OANDA・live・paper未接続 / 取引執行未使用
    </div>
  </header>
  <main>
    <div class="banner {banner_class}">{_esc(banner_text)}</div>

    <div class="banner {ai_state_class}">{_esc(ai_state_text)}</div>

    <section>
      <h2>AI生成状態</h2>
      <p style="line-height:1.7;font-size:13px;margin:0">{ai_lines}</p>
      <p class="muted" style="margin-top:8px">
        OpenAI / Claude のいずれかが「未実行」の状態は、ユーザー確認用の
        完成previewではありません。
        実APIで生成し直すには <code>publish-mvp1-preview</code> workflow
        を手動実行するか、ローカルで OPENAI_API_KEY / ANTHROPIC_API_KEY を
        設定して <code>--mode ai-authored</code> で再生成してください。
      </p>
    </section>

    <section>
      <h2>AI生成 王道判定画面 (OpenAI + Claude が線を設計)</h2>
      <img class="screen" src="./decision_screen.png"
           alt="AI生成 王道判定画面 (観測専用)">
      <p class="muted">
        rendererはAI specを描画するだけです。specに無い線を勝手に追加しません。
        OpenAI案 / Claude案 / 二者比較 / 一致 / 不一致 が
        decision_screen.html / decision_screen.png に表示されます。
      </p>
      <p class="links" style="margin-top:8px">
        <a href="./decision_screen.html">王道判定画面HTMLを開く</a>
        <a href="./dashboard.html">詳細ダッシュボードを開く</a>
      </p>
    </section>

    <section>
      <h2>AI画面設計サマリ</h2>
      <table>{rows}</table>
      <p class="muted">
        OpenAI と Claude が一致しない場合、いずれの判断も画面に並べて表示します。
        システムが片方を勝手に採用することはありません。
      </p>
    </section>

    <section class="links">
      <h2>追加データ</h2>
      <a href="./openai_decision_screen_spec.json">OpenAI画面設計JSON</a>
      <a href="./claude_decision_screen_spec.json">Claude画面設計JSON</a>
      <a href="./decision_screen_spec_compare.json">二者比較JSON</a>
      <a href="./diagnostics.json">診断JSON</a>
      <a href="./review_report.md">AIレビュー集計 (md)</a>
      <a href="./review_report.json">AIレビュー集計 (json)</a>
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
        description="Build the MVP-1 AI-authored decision-screen preview.",
    )
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
    parser.add_argument(
        "--mode",
        choices=["safe-local", "ai-authored"],
        default="safe-local",
        help=(
            "safe-local: strip API keys; AI specs may be UNKNOWN; the "
            "preview is marked 'AI未実行'. "
            "ai-authored: keep API keys; require populated AI specs; "
            "non-zero exit if any provider returned UNKNOWN / empty."
        ),
    )
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

    env = _safe_env(csv_rel, work_rel, mode=args.mode)

    # Preflight: in ai-authored mode, fail fast if API keys are
    # missing so we never produce a UNKNOWN-placeholder preview
    # that's been advertised as AI-generated.
    if args.mode == "ai-authored":
        from ..ai.preflight import check_ai_authored_preview_preflight

        preflight = check_ai_authored_preview_preflight(env)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "preflight.json").write_text(
            json.dumps(preflight.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if not preflight.ok:
            print("AI-authored preflight failed:")
            for tag in preflight.errors:
                print(f"  - {tag}")
            for tag in preflight.warnings:
                print(f"  warning: {tag}")
            print(
                "Non-zero exit. Configure OPENAI_API_KEY and "
                "ANTHROPIC_API_KEY (and OPENAI_ENABLED / "
                "ANTHROPIC_ENABLED) before retrying."
            )
            return 2

    _run([sys.executable, "-m", "fx_monitor.app.run_once"], env=env, cwd=REPO_ROOT)
    _run(
        [
            sys.executable, "-m", "fx_monitor.app.review_report",
            "--log", f"{work_rel}/review_log.jsonl",
            "--md", f"{work_rel}/review_report.md",
            "--json", f"{work_rel}/review_report.json",
        ],
        cwd=REPO_ROOT,
    )
    _run(
        [
            sys.executable, "-m", "fx_monitor.app.dashboard",
            "--diagnostics", f"{work_rel}/diagnostics.json",
            "--summary", f"{work_rel}/review_report.json",
            "--html", f"{work_rel}/dashboard.html",
        ],
        cwd=REPO_ROOT,
    )

    for name in ARTIFACT_FILES:
        src = work_dir / name
        if src.exists():
            shutil.copy2(src, out_dir / name)

    # Build the AI-input pack from the same data the feed pipeline saw.
    from ..ai.claude_reviewer import ClaudeReviewer
    from ..ai.decision_screen_spec_compare import compare_decision_screen_specs
    from ..ai.market_analysis_pack import build_market_analysis_pack
    from ..ai.openai_reviewer import OpenAIReviewer
    from ..analysis import build_royal_road_draft_payload_from_snapshot
    from ..data.csv_feed import load_ohlc_csv
    from ..knowledge.loader import load_knowledge_pack
    from ..render.royal_road_decision_screen import (
        build_royal_road_decision_screen_html,
        render_royal_road_decision_screen_png,
    )

    diag = json.loads((out_dir / "diagnostics.json").read_text(encoding="utf-8"))
    snap = load_ohlc_csv(csv_path, symbol="EURUSD=X", timeframe="M5")
    full_draft = build_royal_road_draft_payload_from_snapshot(snap)
    pack = build_market_analysis_pack(
        snapshot=snap,
        rich_draft=full_draft,
        diagnostics=diag,
        knowledge_pack_text=load_knowledge_pack().text,
    )

    # Ask each AI to author its own decision screen spec. Without API
    # keys (the committed preview default) both come back UNKNOWN.
    from ..ai.decision_screen_spec_schema import (
        validate_decision_screen_spec_for_user_preview,
    )

    openai_reviewer = OpenAIReviewer()
    claude_reviewer = ClaudeReviewer()

    openai_spec = openai_reviewer.build_decision_screen_spec(
        market_analysis_pack=pack
    )
    claude_spec = claude_reviewer.build_decision_screen_spec(
        market_analysis_pack=pack
    )

    repair_log: dict[str, Any] = {"openai": None, "claude": None}

    # One repair pass per provider when the first spec fails the
    # user-preview validation. In safe-local mode the providers are
    # disabled and the repair pass also returns SAFE-UNKNOWN, which
    # is fine — the validator decides whether to fail the run later.
    o_errors = validate_decision_screen_spec_for_user_preview(
        openai_spec, "openai"
    )
    if o_errors:
        prev = openai_spec.model_dump(mode="json")
        repaired = openai_reviewer.repair_decision_screen_spec(
            market_analysis_pack=pack,
            previous_spec=prev,
            validation_errors=o_errors,
        )
        repair_log["openai"] = {
            "first_pass_errors": o_errors,
            "post_repair_errors": validate_decision_screen_spec_for_user_preview(
                repaired, "openai"
            ),
        }
        openai_spec = repaired

    c_errors = validate_decision_screen_spec_for_user_preview(
        claude_spec, "claude"
    )
    if c_errors:
        prev = claude_spec.model_dump(mode="json")
        repaired = claude_reviewer.repair_decision_screen_spec(
            market_analysis_pack=pack,
            previous_spec=prev,
            validation_errors=c_errors,
        )
        repair_log["claude"] = {
            "first_pass_errors": c_errors,
            "post_repair_errors": validate_decision_screen_spec_for_user_preview(
                repaired, "claude"
            ),
        }
        claude_spec = repaired

    comparison = compare_decision_screen_specs(
        openai_spec=openai_spec, claude_spec=claude_spec
    )

    openai_dump = openai_spec.model_dump(mode="json")
    claude_dump = claude_spec.model_dump(mode="json")

    (out_dir / "openai_decision_screen_spec.json").write_text(
        json.dumps(openai_dump, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "claude_decision_screen_spec.json").write_text(
        json.dumps(claude_dump, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "decision_screen_spec_compare.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "decision_screen_repair_log.json").write_text(
        json.dumps(
            {
                "schema_version": "decision_screen_repair_log_v1",
                "openai": repair_log["openai"],
                "claude": repair_log["claude"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    decision_png = out_dir / "decision_screen.png"
    render_royal_road_decision_screen_png(
        openai_spec=openai_dump,
        claude_spec=claude_dump,
        comparison=comparison,
        market_analysis_pack=pack,
        out_path=decision_png,
    )

    decision_html = build_royal_road_decision_screen_html(
        openai_spec=openai_dump,
        claude_spec=claude_dump,
        comparison=comparison,
        market_analysis_pack=pack,
    )
    (out_dir / "decision_screen.html").write_text(decision_html, encoding="utf-8")

    _localize_dashboard_html(out_dir / "dashboard.html")

    for name in (
        "diagnostics.json",
        "review_log.jsonl",
        "review_report.md",
        "review_report.json",
        "openai_decision_screen_spec.json",
        "claude_decision_screen_spec.json",
        "decision_screen_spec_compare.json",
    ):
        _scrub_file(out_dir / name)

    # Remove orphan files from the previous (visual_review) preview design.
    for old in ("visual_review.json",):
        p = out_dir / old
        if p.exists():
            p.unlink()

    ai_state = _ai_execution_state(openai_dump, claude_dump)
    index_html = _render_index_html(
        out_dir,
        openai_dump,
        claude_dump,
        comparison,
        mode=args.mode,
        ai_state=ai_state,
    )
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")

    # ai-authored mode: empty / UNKNOWN / safety-flag-violating specs
    # are a hard failure. The preview directory has already been
    # written so an operator can see WHY it failed, but the process
    # exits non-zero so CI fails loudly.
    validation_errors: list[str] = []
    if args.mode == "ai-authored":
        validation_errors = _validate_ai_authored_specs(openai_dump, claude_dump)

    files = [
        "index.html",
        "decision_screen.html",
        "decision_screen.png",
        "openai_decision_screen_spec.json",
        "claude_decision_screen_spec.json",
        "decision_screen_spec_compare.json",
        "dashboard.html",
        "draft_chart.png",
        "diagnostics.json",
        "review_report.md",
        "review_report.json",
        "review_log.jsonl",
    ]
    print(f"Preview written to: {out_dir} (mode={args.mode})")
    for name in files:
        p = out_dir / name
        size = p.stat().st_size if p.exists() else 0
        print(f"  {name:<38}: {size} B")
    print(
        "AI execution state: "
        f"openai={'executed' if ai_state['openai']['executed'] else 'NOT RUN'} "
        f"({ai_state['openai']['final_status']}), "
        f"claude={'executed' if ai_state['claude']['executed'] else 'NOT RUN'} "
        f"({ai_state['claude']['final_status']})"
    )
    if args.mode == "ai-authored" and validation_errors:
        print("ai-authored validation failed:")
        for tag in validation_errors:
            print(f"  - {tag}")
        print(
            "Non-zero exit. The committed preview directory has been "
            "written but it is NOT a user-facing AI-authored preview."
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
