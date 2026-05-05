"""Static-HTML dashboard for the corpus.

Renders ``docs/live_dashboard/index.html`` and per-entry detail pages
under ``docs/live_dashboard/entries/<id>.html``. No JavaScript, no
external services — opening ``index.html`` in a browser via
``file://`` is enough.

The per-entry page now embeds:

- Chart PNG (candles + AI lines + pivot labels + future bars + wave
  skeleton) via :mod:`fx_monitor.render.entry_chart`.
- Procedure-step grid with PASS/WAIT/UNKNOWN badges and reason text.
- Post-mortem analysis (failure mode, suspected weak steps,
  countermeasures) for entries with LOSE / NEUTRAL_MISSED outcomes.
- Raw-data sections (market pack, full spec, prompt) collapsed by
  default for audit / investigation.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Sequence

from fx_monitor.corpus.schema import CorpusEntry
from fx_monitor.corpus.store import JsonlVectorStore
from fx_monitor.live.candle import Candle
from fx_monitor.postmortem.analyzer import Postmortem, analyze
from fx_monitor.render.entry_chart import render_entry_chart_png

from ._paths import corpus_root, pending_judgement_path, repo_root


FetchFutureFn = Callable[[str, datetime, int], list[Candle]]


_CSS = """
:root { color-scheme: light dark; }
body {
    font-family: -apple-system, system-ui, "Segoe UI", sans-serif;
    margin: 0; padding: 1.5rem;
    background: #0b1220; color: #e2e8f0; line-height: 1.5;
}
header { border-bottom: 1px solid #334155; padding-bottom: 1rem; margin-bottom: 1.5rem; }
h1 { margin: 0; font-size: 1.6rem; }
h2 { margin-top: 1.6rem; font-size: 1.15rem; border-bottom: 1px solid #1e293b; padding-bottom: 0.3rem; }
h3 { margin-top: 1.2rem; font-size: 1rem; color: #cbd5e1; }
.meta { color: #94a3b8; font-size: 0.9rem; }
.grid {
    display: grid; gap: 1rem;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    margin: 1rem 0;
}
.card { background: #111a2c; border: 1px solid #1e293b; border-radius: 6px; padding: 1rem; }
.card .label { color: #94a3b8; font-size: 0.85rem; }
.card .value { font-size: 1.4rem; font-weight: 600; margin-top: 0.25rem; }
.safety {
    background: #422006; border-left: 4px solid #ea580c;
    padding: 0.6rem 1rem; border-radius: 4px; margin: 1rem 0; font-size: 0.9rem;
}
.postmortem {
    background: #1e1b3b; border-left: 4px solid #a78bfa;
    padding: 0.8rem 1rem; border-radius: 4px; margin: 1rem 0;
}
.postmortem.severity-high { border-left-color: #ef4444; background: #2c1414; }
.postmortem.severity-medium { border-left-color: #f59e0b; background: #2c1f0a; }
.postmortem h3 { margin-top: 0; color: #c4b5fd; }
.postmortem.severity-high h3 { color: #fca5a5; }
.postmortem.severity-medium h3 { color: #fcd34d; }
table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; font-size: 0.9rem; }
th, td { padding: 0.5rem 0.75rem; border-bottom: 1px solid #1e293b; text-align: left; vertical-align: top; }
th { background: #111a2c; color: #94a3b8; font-weight: 500; }
tr:hover td { background: #0f172a; }
.badge {
    display: inline-block; padding: 0.15rem 0.5rem;
    border-radius: 999px; font-size: 0.75rem; font-weight: 600;
}
.badge-WIN, .badge-PASS { background: #064e3b; color: #6ee7b7; }
.badge-LOSE, .badge-BLOCK { background: #7f1d1d; color: #fca5a5; }
.badge-NEUTRAL_GOOD, .badge-WAIT { background: #1e3a8a; color: #93c5fd; }
.badge-NEUTRAL_MISSED, .badge-WARN { background: #713f12; color: #fcd34d; }
.badge-PENDING, .badge-UNKNOWN { background: #334155; color: #cbd5e1; }
.badge-DISSENT { background: #4c1d95; color: #c4b5fd; margin-left: 0.5rem; }
.steps {
    display: grid; gap: 0.4rem;
    grid-template-columns: auto auto 1fr;
    align-items: center;
    margin-top: 0.6rem;
    font-size: 0.88rem;
}
.steps .num { color: #64748b; font-variant-numeric: tabular-nums; }
.steps .key { color: #cbd5e1; min-width: 11rem; }
.steps .reason { color: #94a3b8; }
a { color: #60a5fa; text-decoration: none; }
a:hover { text-decoration: underline; }
pre {
    background: #0f172a; padding: 1rem; border-radius: 6px;
    overflow: auto; font-size: 0.82rem; max-height: 24rem;
}
details { margin: 0.6rem 0; }
details summary { cursor: pointer; color: #93c5fd; font-size: 0.92rem; padding: 0.4rem 0; }
details[open] summary { color: #60a5fa; }
.chart-img { width: 100%; max-width: 100%; height: auto; border-radius: 6px; margin-top: 0.6rem; }
"""

_SAFETY_BANNER = (
    "観測専用ダッシュボード — このシステムは READY 通知 / 自動売買 / "
    "手動売買連動を行いません。表示はあくまで参考材料です。"
)


def _esc(s: object) -> str:
    return html.escape(str(s) if s is not None else "")


def _badge(status: str) -> str:
    return f'<span class="badge badge-{_esc(status)}">{_esc(status)}</span>'


def _format_entry_summary(entry: CorpusEntry) -> str:
    asof = entry.asof_utc.strftime("%Y-%m-%d %H:%M UTC")
    dissent = ' <span class="badge badge-DISSENT">DISSENT</span>' if entry.user_dissent else ""
    fav = entry.outcome.max_favorable_pip
    adv = entry.outcome.max_adverse_pip
    fav_s = f"{fav:+.1f}" if fav is not None else "—"
    adv_s = f"{adv:+.1f}" if adv is not None else "—"
    return (
        "<tr>"
        f"<td>{_esc(asof)}</td>"
        f"<td>{_esc(entry.symbol)}</td>"
        f"<td>{_esc(entry.judgement.side)}</td>"
        f"<td>{_esc(entry.judgement.final_status)}</td>"
        f"<td>{_badge(entry.outcome.status)}{dissent}</td>"
        f"<td>{_esc(fav_s)} / {_esc(adv_s)} pip</td>"
        f'<td><a href="entries/{_esc(entry.entry_id)}.html">{_esc(entry.entry_id[:8])}…</a></td>'
        "</tr>"
    )


def render_index(entries: list[CorpusEntry], *, generated_at: datetime, days: int = 30) -> str:
    cutoff = generated_at - timedelta(days=days)
    recent = [
        e for e in entries
        if (e.asof_utc.replace(tzinfo=timezone.utc) if e.asof_utc.tzinfo is None else e.asof_utc) >= cutoff
    ]
    recent.sort(
        key=lambda e: e.asof_utc if e.asof_utc.tzinfo else e.asof_utc.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    outcome_counts = Counter(e.outcome.status for e in recent)
    final_status_counts = Counter(e.judgement.final_status for e in recent)
    scored = [e for e in recent if e.outcome.status in ("WIN", "LOSE")]
    win_rate = (
        sum(1 for e in scored if e.outcome.status == "WIN") / len(scored)
        if scored else None
    )
    dissent = sum(1 for e in recent if e.user_dissent)
    actionable = sum(
        1 for e in recent if e.outcome.status in ("LOSE", "NEUTRAL_MISSED")
    )

    cards = [
        ("総コーパス件数", str(len(entries))),
        (f"直近{days}日の判定数", str(len(recent))),
        ("WIN/LOSE 採点済", str(len(scored))),
        ("WIN率", f"{win_rate:.1%}" if win_rate is not None else "—"),
        ("PENDING", str(outcome_counts.get("PENDING", 0))),
        ("要分析(LOSE/MISSED)", str(actionable)),
        ("違和感フラグ", str(dissent)),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="label">{_esc(label)}</div>'
        f'<div class="value">{_esc(value)}</div></div>'
        for label, value in cards
    )

    rows = "".join(_format_entry_summary(e) for e in recent[:200])
    if not rows:
        rows = '<tr><td colspan="7" style="text-align:center; color:#94a3b8;">コーパス未蓄積</td></tr>'

    fs_breakdown = ", ".join(
        f"{k}={v}" for k, v in sorted(final_status_counts.items())
    ) or "—"

    return f"""<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="utf-8"><title>Royal-road dashboard</title>
<style>{_CSS}</style>
</head><body>
<header>
<h1>王道判定ダッシュボード</h1>
<div class="meta">生成 {_esc(generated_at.strftime("%Y-%m-%d %H:%M UTC"))} ・ 直近 {days} 日</div>
</header>
<div class="safety">{_esc(_SAFETY_BANNER)}</div>
<div class="grid">{cards_html}</div>
<h2>final_status 内訳</h2>
<p class="meta">{_esc(fs_breakdown)}</p>
<h2>判定一覧 (新しい順, 最大200件)</h2>
<table>
<thead><tr>
<th>asof (UTC)</th><th>symbol</th><th>side</th><th>final_status</th>
<th>outcome</th><th>fav / adv</th><th>id</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>
</body></html>
"""


def _render_steps_block(entry: CorpusEntry) -> str:
    parts: list[str] = ['<div class="steps">']
    for i, step in enumerate(entry.judgement.procedure_steps, 1):
        label = getattr(step, "label_ja", None) or step.key
        result = getattr(step, "result_ja", "") or ""
        parts.append(
            f'<div class="num">{i:02d}.</div>'
            f'<div class="key">{_esc(label)} <span class="meta">({_esc(step.key)})</span></div>'
            f'<div>{_badge(step.status)} <span class="reason">{_esc(result)}</span></div>'
        )
    parts.append("</div>")
    return "".join(parts)


def _render_lines_table(entry: CorpusEntry) -> str:
    if not entry.judgement.lines:
        return '<p class="meta">lines: なし</p>'
    rows = []
    for line in entry.judgement.lines:
        anchors = ",".join(line.anchor_points) if line.anchor_points else "-"
        rows.append(
            "<tr>"
            f"<td>{_esc(line.id)}</td><td>{_esc(line.label)}</td>"
            f"<td>{_esc(line.kind)}</td><td>{_esc(line.role)}</td>"
            f"<td>{_esc(f'{line.price:.5f}' if line.price is not None else '—')}</td>"
            f"<td>{_esc(anchors)}</td>"
            f"<td class='reason'>{_esc(line.reason_ja)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>id</th><th>label</th><th>kind</th><th>role</th>"
        "<th>price</th><th>anchors</th><th>reason</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _render_points_table(entry: CorpusEntry) -> str:
    if not entry.judgement.points:
        return '<p class="meta">points: なし</p>'
    rows = []
    for p in entry.judgement.points:
        rows.append(
            "<tr>"
            f"<td>{_esc(p.id)}</td><td>{_esc(p.label)}</td><td>{_esc(p.role)}</td>"
            f"<td>{_esc(p.index)}</td>"
            f"<td>{_esc(f'{p.price:.5f}' if p.price is not None else '—')}</td>"
            f"<td class='reason'>{_esc(p.reason_ja)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>id</th><th>label</th><th>role</th><th>index</th>"
        "<th>price</th><th>reason</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _render_postmortem(pm: Postmortem) -> str:
    facts = "".join(f"<li>{_esc(f)}</li>" for f in pm.facts_ja)
    suspicions = "".join(
        "<tr>"
        f"<td>{_esc(s.step_key)}</td>"
        f"<td>{_badge(s.step_status)}</td>"
        f"<td>{_esc(s.note_ja)}</td>"
        "</tr>"
        for s in pm.step_suspicions
    )
    countermeasures = "".join(f"<li>{_esc(c)}</li>" for c in pm.countermeasures_ja)
    sev = pm.severity
    return f"""<section class="postmortem severity-{_esc(sev)}">
<h3>後付け分析 (severity: {_esc(sev)} / failure_mode: {_esc(pm.failure_mode)})</h3>
<p><strong>{_esc(pm.headline_ja)}</strong></p>
<h4 class="meta">事実(60本後の price action)</h4>
<ul>{facts}</ul>
<h4 class="meta">疑わしい procedure step</h4>
{'<table><thead><tr><th>step</th><th>当時のstatus</th><th>所見</th></tr></thead><tbody>' + suspicions + '</tbody></table>' if suspicions else '<p class="meta">特になし</p>'}
<h4 class="meta">具体的な対策案</h4>
{'<ul>' + countermeasures + '</ul>' if countermeasures else '<p class="meta">対策案なし</p>'}
</section>
"""


def _render_raw_sections(entry: CorpusEntry) -> str:
    spec_json = json.dumps(entry.judgement.model_dump(mode="json"), ensure_ascii=False, indent=2)
    pack_json = json.dumps(entry.market_pack.model_dump(mode="json"), ensure_ascii=False, indent=2)
    prompt_path = pending_judgement_path(entry.entry_id).with_suffix(".prompt.md")
    prompt_text = ""
    if prompt_path.exists():
        prompt_text = prompt_path.read_text(encoding="utf-8")

    sections = [
        '<details><summary>raw: AI 判定 (AiDecisionScreenSpec JSON)</summary>'
        f'<pre>{_esc(spec_json)}</pre></details>',
        '<details><summary>raw: 数値事実 pack (MarketAnalysisPackV2 JSON, OHLC全件含む)</summary>'
        f'<pre>{_esc(pack_json)}</pre></details>',
    ]
    if prompt_text:
        sections.append(
            '<details><summary>raw: AI に渡されたプロンプト全文</summary>'
            f'<pre>{_esc(prompt_text)}</pre></details>'
        )
    sections.append(
        '<details><summary>raw: 特徴ベクトル (272次元)</summary>'
        f'<pre>{_esc(json.dumps(entry.feature_vector))}</pre></details>'
    )
    return "".join(sections)


def render_entry_page(
    entry: CorpusEntry,
    *,
    generated_at: datetime,
    chart_filename: str | None = None,
    postmortem: Postmortem | None = None,
) -> str:
    pack = entry.market_pack
    outcome = entry.outcome
    fav = outcome.max_favorable_pip
    adv = outcome.max_adverse_pip
    fav_s = f"{fav:+.1f}" if fav is not None else "—"
    adv_s = f"{adv:+.1f}" if adv is not None else "—"
    pack_summary = (
        f"asof={pack.asof_utc.isoformat()} session={pack.session} "
        f"current={pack.current_price:.5f} atr_m5={pack.atr.m5_14:.5f} "
        f"24h_range=[{pack.recent_range.low_24h:.5f}..{pack.recent_range.high_24h:.5f}] "
        f"candles={len(pack.candles)} pivots={len(pack.pivots)}"
    )

    chart_html = ""
    if chart_filename:
        chart_html = (
            f'<h2>判定時点のチャート + AI ライン</h2>'
            f'<img class="chart-img" src="{_esc(chart_filename)}" '
            f'alt="entry chart for {_esc(entry.entry_id)}">'
        )

    postmortem_html = _render_postmortem(postmortem) if postmortem else ""

    return f"""<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="utf-8"><title>判定 {_esc(entry.entry_id[:8])}</title>
<style>{_CSS}</style>
</head><body>
<header>
<h1>判定詳細</h1>
<div class="meta"><a href="../index.html">← 一覧に戻る</a></div>
</header>
<div class="safety">{_esc(_SAFETY_BANNER)}</div>

<div class="grid">
<div class="card"><div class="label">entry_id</div><div class="value" style="font-size:1rem;">{_esc(entry.entry_id)}</div></div>
<div class="card"><div class="label">asof_utc</div><div class="value" style="font-size:1rem;">{_esc(entry.asof_utc.isoformat())}</div></div>
<div class="card"><div class="label">symbol / timeframe</div><div class="value" style="font-size:1rem;">{_esc(entry.symbol)} / {_esc(entry.timeframe)}</div></div>
<div class="card"><div class="label">judgement</div><div class="value" style="font-size:1rem;">{_esc(entry.judgement.side)} · {_esc(entry.judgement.final_status)}</div></div>
<div class="card"><div class="label">outcome</div><div class="value">{_badge(outcome.status)}</div></div>
<div class="card"><div class="label">favourable / adverse</div><div class="value" style="font-size:1rem;">{_esc(fav_s)} / {_esc(adv_s)} pip</div></div>
<div class="card"><div class="label">user dissent</div><div class="value" style="font-size:1rem;">{_esc("Yes" if entry.user_dissent else "No")}</div></div>
<div class="card"><div class="label">judgement model</div><div class="value" style="font-size:1rem;">{_esc(entry.judgement_model)}</div></div>
</div>

{chart_html}

{postmortem_html}

<h2>AI が下した判定の物語</h2>
<p>{_esc(entry.judgement.market_story_ja or "(空)")}</p>
<p class="meta"><strong>パターンラベル:</strong> {_esc(entry.judgement.pattern_label_ja or "—")}</p>
<p class="meta"><strong>サマリ:</strong> {_esc(entry.judgement.summary_ja or "—")}</p>

<h2>王道14手順チェック</h2>
{_render_steps_block(entry)}

<h2>AI が引いた lines</h2>
{_render_lines_table(entry)}

<h2>AI が指したピボット (points)</h2>
{_render_points_table(entry)}

<h2>市場パック概要</h2>
<pre>{_esc(pack_summary)}</pre>

<h2>調査用: raw データ</h2>
{_render_raw_sections(entry)}

<p class="meta" style="margin-top: 2rem;">違和感を立てる場合: <code>python -m fx_monitor.tools.flag_dissent --id {_esc(entry.entry_id)} --note "..."</code></p>
</body></html>
"""


def generate_dashboard(
    *,
    corpus_name: str = "default",
    days: int = 30,
    output_root: Path | None = None,
    now_utc: datetime | None = None,
    fetch_future: FetchFutureFn | None = None,
    lookahead_bars: int = 60,
    render_charts: bool = True,
) -> dict:
    """Render the dashboard.

    ``fetch_future`` is optional; when supplied, future candles are
    appended to the chart in muted grey and a post-mortem is generated
    for failed entries. Without it, the chart shows only the past
    window the AI saw.
    """
    now = now_utc or datetime.now(timezone.utc)
    store = JsonlVectorStore(corpus_root(corpus_name))
    entries = store.all()

    out = output_root or (repo_root() / "docs" / "live_dashboard")
    out.mkdir(parents=True, exist_ok=True)
    (out / "entries").mkdir(parents=True, exist_ok=True)

    index_html = render_index(entries, generated_at=now, days=days)
    (out / "index.html").write_text(index_html, encoding="utf-8")

    cutoff = now - timedelta(days=days)
    written = 0
    charts_rendered = 0
    postmortems_generated = 0

    for e in entries:
        asof = e.asof_utc if e.asof_utc.tzinfo else e.asof_utc.replace(tzinfo=timezone.utc)
        if asof < cutoff:
            continue

        future: list[Candle] = []
        if fetch_future is not None:
            try:
                future = fetch_future(e.symbol, asof, lookahead_bars)
            except Exception:
                future = []

        chart_filename: str | None = None
        if render_charts:
            chart_path = out / "entries" / f"{e.entry_id}.png"
            try:
                render_entry_chart_png(
                    e, out_path=chart_path, future_candles=future,
                )
                chart_filename = f"{e.entry_id}.png"
                charts_rendered += 1
            except Exception:
                chart_filename = None

        pm: Postmortem | None = None
        if future and e.outcome.status in ("LOSE", "NEUTRAL_MISSED", "WIN", "NEUTRAL_GOOD"):
            pm = analyze(e, future)
            if pm.failure_mode in ("no_post_mortem_needed", "outcome_pending"):
                pm = None
            else:
                postmortems_generated += 1

        page = render_entry_page(
            e, generated_at=now,
            chart_filename=chart_filename,
            postmortem=pm,
        )
        (out / "entries" / f"{e.entry_id}.html").write_text(page, encoding="utf-8")
        written += 1

    return {
        "output_root": str(out),
        "total_entries": len(entries),
        "entry_pages_written": written,
        "charts_rendered": charts_rendered,
        "postmortems_generated": postmortems_generated,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fx_monitor.tools.dashboard")
    p.add_argument("--corpus-name", default="default")
    p.add_argument("--days", type=int, default=30)
    p.add_argument(
        "--archive-file",
        type=Path,
        default=None,
        help="Optional OHLC JSON archive to source future candles for post-mortem.",
    )
    args = p.parse_args(argv)

    fetcher: FetchFutureFn | None = None
    if args.archive_file and args.archive_file.exists():
        records = json.loads(args.archive_file.read_text(encoding="utf-8"))
        archive = [
            Candle(
                t=datetime.fromisoformat(r["t"]),
                o=r["o"], h=r["h"], l=r["l"], c=r["c"],
                v=r.get("v"),
            )
            for r in records
        ]

        def _fetch(symbol: str, asof: datetime, n: int) -> list[Candle]:
            if asof.tzinfo is None:
                asof = asof.replace(tzinfo=timezone.utc)
            future = [c for c in archive if c.t > asof]
            return future[:n]

        fetcher = _fetch

    info = generate_dashboard(
        corpus_name=args.corpus_name, days=args.days, fetch_future=fetcher
    )
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
