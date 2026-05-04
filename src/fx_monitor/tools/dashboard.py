"""Static-HTML dashboard for the corpus.

Renders ``docs/live_dashboard/index.html`` and per-entry detail pages
under ``docs/live_dashboard/entries/<id>.html``. No JavaScript, no
external services — opening ``index.html`` in a browser via
``file://`` is enough.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fx_monitor.corpus.schema import CorpusEntry
from fx_monitor.corpus.store import JsonlVectorStore

from ._paths import corpus_root, repo_root


_CSS = """
:root { color-scheme: light dark; }
body {
    font-family: -apple-system, system-ui, "Segoe UI", sans-serif;
    margin: 0;
    padding: 1.5rem;
    background: #0b1220;
    color: #e2e8f0;
    line-height: 1.5;
}
header {
    border-bottom: 1px solid #334155;
    padding-bottom: 1rem;
    margin-bottom: 1.5rem;
}
h1 { margin: 0; font-size: 1.6rem; }
.meta { color: #94a3b8; font-size: 0.9rem; }
.grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1rem;
    margin: 1rem 0;
}
.card {
    background: #111a2c;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 1rem;
}
.card .label { color: #94a3b8; font-size: 0.85rem; }
.card .value { font-size: 1.4rem; font-weight: 600; margin-top: 0.25rem; }
.safety {
    background: #422006;
    border-left: 4px solid #ea580c;
    padding: 0.6rem 1rem;
    border-radius: 4px;
    margin: 1rem 0;
    font-size: 0.9rem;
}
table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 1rem;
    font-size: 0.9rem;
}
th, td {
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid #1e293b;
    text-align: left;
}
th { background: #111a2c; color: #94a3b8; font-weight: 500; }
tr:hover td { background: #0f172a; }
.badge {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
}
.badge-WIN { background: #064e3b; color: #6ee7b7; }
.badge-LOSE { background: #7f1d1d; color: #fca5a5; }
.badge-NEUTRAL_GOOD { background: #1e3a8a; color: #93c5fd; }
.badge-NEUTRAL_MISSED { background: #713f12; color: #fcd34d; }
.badge-PENDING { background: #334155; color: #cbd5e1; }
.badge-DISSENT { background: #4c1d95; color: #c4b5fd; margin-left: 0.5rem; }
a { color: #60a5fa; text-decoration: none; }
a:hover { text-decoration: underline; }
pre {
    background: #0f172a;
    padding: 1rem;
    border-radius: 6px;
    overflow: auto;
    font-size: 0.85rem;
}
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
        if (e.asof_utc.replace(tzinfo=timezone.utc) if e.asof_utc.tzinfo is None else e.asof_utc)
        >= cutoff
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
        if scored
        else None
    )
    dissent = sum(1 for e in recent if e.user_dissent)

    cards = [
        ("総コーパス件数", str(len(entries))),
        (f"直近{days}日の判定数", str(len(recent))),
        ("WIN/LOSE 採点済", str(len(scored))),
        ("WIN率", f"{win_rate:.1%}" if win_rate is not None else "—"),
        ("PENDING", str(outcome_counts.get("PENDING", 0))),
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
<meta charset="utf-8">
<title>Royal-road dashboard</title>
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


def render_entry_page(entry: CorpusEntry, *, generated_at: datetime) -> str:
    spec_json = json.dumps(entry.judgement.model_dump(mode="json"), ensure_ascii=False, indent=2)
    pack = entry.market_pack
    pack_summary = (
        f"asof={pack.asof_utc.isoformat()} "
        f"session={pack.session} "
        f"current={pack.current_price:.5f} "
        f"atr_m5={pack.atr.m5_14:.5f} "
        f"24h_range=[{pack.recent_range.low_24h:.5f}..{pack.recent_range.high_24h:.5f}]"
    )
    outcome = entry.outcome
    fav = outcome.max_favorable_pip
    adv = outcome.max_adverse_pip
    fav_s = f"{fav:+.1f}" if fav is not None else "—"
    adv_s = f"{adv:+.1f}" if adv is not None else "—"

    return f"""<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="utf-8">
<title>判定 {_esc(entry.entry_id[:8])}</title>
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
<h2>市場パック概要</h2>
<pre>{_esc(pack_summary)}</pre>
<h2>AI 判定 (AiDecisionScreenSpec)</h2>
<pre>{_esc(spec_json)}</pre>
<p class="meta">違和感を立てる場合: <code>python -m fx_monitor.tools.flag_dissent --id {_esc(entry.entry_id)} --note "..."</code></p>
</body></html>
"""


def generate_dashboard(
    *,
    corpus_name: str = "default",
    days: int = 30,
    output_root: Path | None = None,
    now_utc: datetime | None = None,
) -> dict:
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
    for e in entries:
        asof = e.asof_utc if e.asof_utc.tzinfo else e.asof_utc.replace(tzinfo=timezone.utc)
        if asof < cutoff:
            continue
        page = render_entry_page(e, generated_at=now)
        (out / "entries" / f"{e.entry_id}.html").write_text(page, encoding="utf-8")
        written += 1

    return {
        "output_root": str(out),
        "total_entries": len(entries),
        "entry_pages_written": written,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fx_monitor.tools.dashboard")
    p.add_argument("--corpus-name", default="default")
    p.add_argument("--days", type=int, default=30)
    args = p.parse_args(argv)

    info = generate_dashboard(corpus_name=args.corpus_name, days=args.days)
    print(json.dumps(info, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
