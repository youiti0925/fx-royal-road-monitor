"""Render an offline HTML dashboard from diagnostics.json + review_report.json.

The dashboard is read-only and intentionally never includes live links,
data fetches, or scripts that could side-effect anything. It is meant to
be opened from a downloaded artifact archive and inspected by a human.

It is not used for:

- READY decisions
- notifications
- trading or order execution
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def _load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _dict_items_table(data: dict[str, Any] | None) -> str:
    if not data:
        return "<p class='muted'>No data</p>"
    rows = []
    for k, v in data.items():
        rows.append(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>")
    return "<table>" + "\n".join(rows) + "</table>"


def _top_list(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return "<p class='muted'>No items</p>"
    rows = []
    for item in items:
        rows.append(
            "<tr>"
            f"<td>{_esc(item.get('value', ''))}</td>"
            f"<td class='num'>{_esc(item.get('count', ''))}</td>"
            "</tr>"
        )
    return (
        "<table><tr><th>value</th><th>count</th></tr>"
        + "\n".join(rows)
        + "</table>"
    )


def build_dashboard_html(
    *,
    diagnostics: dict[str, Any],
    review_summary: dict[str, Any],
) -> str:
    feed = diagnostics.get("feed") or {}
    draft = diagnostics.get("draft") or {}
    rich_draft = draft.get("rich_draft") or {}
    rule = diagnostics.get("rule") or {}
    ai = diagnostics.get("ai") or {}
    decision = diagnostics.get("decision") or {}
    safety = diagnostics.get("safety") or {}

    openai = ai.get("openai") or {}
    claude = ai.get("claude") or {}
    compare = ai.get("compare") or {}

    summary_safety = review_summary.get("safety") or {}
    used_for_ready = summary_safety.get("used_for_ready")
    used_for_notification = summary_safety.get("used_for_notification")

    rich_ready_eligible = rich_draft.get("ready_eligible")
    rich_p0_pass = rich_draft.get("p0_pass")

    safety_ok = (
        decision.get("level") == "SUPPRESSED"
        and safety.get("ready_allowed") is False
        and safety.get("dispatch_called") is False
        and used_for_ready is False
        and used_for_notification is False
        # Phase P1 invariant: rich draft must never claim READY eligibility
        # or a passing P0 checklist. If either is set, flip the banner red.
        and (rich_ready_eligible is None or rich_ready_eligible is False)
        and (rich_p0_pass is None or rich_p0_pass is False)
    )

    safety_class = "ok" if safety_ok else "bad"
    safety_text = (
        "SAFE: offline analysis only"
        if safety_ok
        else "CHECK SAFETY FLAGS"
    )

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>FX Monitor Draft Review Dashboard</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Noto Sans CJK JP",
        "Noto Sans JP", "Yu Gothic", "Meiryo", sans-serif;
      background: #f4f7fb;
      color: #172033;
    }}
    header {{
      padding: 20px 28px;
      background: #0f172a;
      color: white;
    }}
    h1 {{ margin: 0; font-size: 24px; }}
    .sub {{ color: #cbd5e1; margin-top: 6px; }}
    main {{ padding: 24px; }}
    .safety {{
      padding: 16px 18px;
      border-radius: 14px;
      margin-bottom: 18px;
      font-weight: 700;
    }}
    .safety.ok {{ background: #dcfce7; color: #166534; }}
    .safety.bad {{ background: #fee2e2; color: #991b1b; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
    }}
    .card {{
      background: white;
      border: 1px solid #dbe4f0;
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 8px 24px rgba(15, 23, 42, .06);
    }}
    .wide {{ grid-column: span 2; }}
    .full {{ grid-column: 1 / -1; }}
    h2 {{ font-size: 16px; margin: 0 0 10px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #e5eaf2; padding: 7px 6px;
              text-align: left; vertical-align: top; }}
    th {{ color: #475569; width: 38%; }}
    .num {{ text-align: right; }}
    .muted {{ color: #64748b; }}
    .pill {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 999px;
      background: #e2e8f0;
      font-size: 12px;
      font-weight: 700;
    }}
    .suppressed {{ background: #fee2e2; color: #991b1b; }}
    footer {{ color: #64748b; font-size: 12px; padding: 24px; }}
  </style>
</head>
<body>
  <header>
    <h1>FX Monitor Draft Review Dashboard</h1>
    <div class="sub">offline artifact / not used for READY / not used for notification</div>
  </header>
  <main>
    <div class="safety {safety_class}">{_esc(safety_text)}</div>

    <section class="grid">
      <div class="card">
        <h2>Feed</h2>
        {_dict_items_table(feed)}
      </div>

      <div class="card">
        <h2>Draft</h2>
        {_dict_items_table({k: v for k, v in draft.items() if k != "rich_draft"})}
      </div>

      <div class="card">
        <h2>Rich draft</h2>
        {_dict_items_table(rich_draft)}
      </div>

      <div class="card">
        <h2>Decision</h2>
        <p><span class="pill suppressed">{_esc(decision.get("level", "UNKNOWN"))}</span></p>
        {_dict_items_table(decision)}
      </div>

      <div class="card">
        <h2>Rule</h2>
        {_dict_items_table(rule)}
      </div>

      <div class="card">
        <h2>OpenAI</h2>
        {_dict_items_table(openai)}
      </div>

      <div class="card">
        <h2>Claude</h2>
        {_dict_items_table(claude)}
      </div>

      <div class="card">
        <h2>Compare</h2>
        {_dict_items_table(compare)}
      </div>

      <div class="card">
        <h2>Review summary</h2>
        {_dict_items_table({
            "total_records": review_summary.get("total_records"),
            "invalid_records": review_summary.get("invalid_records"),
            "decisions": review_summary.get("decisions"),
            "compare_results": review_summary.get("compare_results"),
        })}
      </div>

      <div class="card">
        <h2>Safety flags</h2>
        {_dict_items_table({
            "diagnostics.ready_allowed": safety.get("ready_allowed"),
            "diagnostics.dispatch_called": safety.get("dispatch_called"),
            "summary.used_for_ready": used_for_ready,
            "summary.used_for_notification": used_for_notification,
            "offline_analysis_only": summary_safety.get("offline_analysis_only"),
        })}
      </div>

      <div class="card wide">
        <h2>Top OpenAI missing</h2>
        {_top_list(review_summary.get("top_openai_missing"))}
      </div>

      <div class="card">
        <h2>Top Claude missing</h2>
        {_top_list(review_summary.get("top_claude_missing"))}
      </div>

      <div class="card wide">
        <h2>Top OpenAI disagreements</h2>
        {_top_list(review_summary.get("top_openai_disagreements"))}
      </div>

      <div class="card">
        <h2>Top Claude disagreements</h2>
        {_top_list(review_summary.get("top_claude_disagreements"))}
      </div>
    </section>
  </main>
  <footer>
    This dashboard is generated from diagnostics.json and review_report.json.
    It is never used for trading, READY decisions, or notifications.
  </footer>
</body>
</html>
"""


def write_dashboard(
    *,
    diagnostics_path: str | Path,
    review_summary_path: str | Path,
    html_path: str | Path,
) -> Path:
    diagnostics = _load_json(diagnostics_path)
    review_summary = _load_json(review_summary_path)
    html_text = build_dashboard_html(
        diagnostics=diagnostics,
        review_summary=review_summary,
    )

    out = Path(html_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8")
    return out


__all__ = ["build_dashboard_html", "write_dashboard"]
