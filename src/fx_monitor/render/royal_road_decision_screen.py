"""王道判定画面 — Japanese-UI decision screen.

This module renders **two** outputs from the same ``rich_draft`` data:

- ``build_royal_road_decision_screen_html(...)``:
  a self-contained HTML string with inline SVG. CSS class names follow
  the ``rr-*`` convention (rr-screen / rr-safety-header / rr-main /
  rr-chart-panel / rr-checklist-panel / rr-ai-visual-review and the
  geometry classes rr-wave-skeleton-line / rr-pivot-dot / rr-pivot-label
  / rr-wnl-line / rr-wsl-line / rr-wtp-line / rr-structural-neckline
  / rr-structural-invalidation / rr-structural-target /
  rr-structural-trendline / rr-sr-zone / rr-safety-watermark).

- ``render_royal_road_decision_screen_png(...)``:
  a matplotlib PNG that AI providers (OpenAI / Claude) can grade
  visually. The PNG carries the same observation-only watermarks as
  the HTML.

Neither output is used for READY decisions, notification dispatch,
trading, or order execution. Both carry safety watermarks so a
screenshot can never be mistaken for a tradeable signal.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

# CSS palette mirrors the existing dashboard so the look is consistent.
COLORS = {
    "bg": "#f4f7fb",
    "panel": "#ffffff",
    "grid": "#d9e2ef",
    "text": "#172033",
    "muted": "#60708a",
    "wave": "#2563eb",
    "neckline": "#7c3aed",
    "stop": "#dc2626",
    "target": "#16a34a",
    "structure": "#0f766e",
    "numeric": "#60a5fa",
    "ready": "#16a34a",
    "wait": "#f59e0b",
    "block": "#ef4444",
    "unknown": "#94a3b8",
}

_DEFAULT_PART_X_INDEX = {"P1": 5, "B1": 5, "NL": 10, "P2": 15, "B2": 15, "BR": 20}

CHECKLIST_LABELS_JA: list[tuple[str, str]] = [
    ("environment", "環境認識"),
    ("htf_direction", "上位足方向"),
    ("dow_structure", "ダウ理論"),
    ("support_resistance", "重要水平線"),
    ("trendline_context", "トレンドライン"),
    ("wave_pattern", "波形認識"),
    ("wave_lines", "Wライン"),
    ("breakout_confirmed", "ブレイク確認"),
    ("retest_confirmed", "リターンムーブ"),
    ("confirmation_candle", "ローソク足確認"),
    ("entry_price", "ENTRY候補"),
    ("stop_price", "STOP候補"),
    ("target_price", "TP候補"),
    ("rr_ok", "RR"),
    ("event_clear", "イベント確認"),
]

STATUS_JA = {
    "PASS": "達成",
    "WAIT": "待機",
    "WARN": "注意",
    "BLOCK": "禁止",
    "UNKNOWN": "未確認",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _esc(value: Any) -> str:
    return html.escape(str(value))


def _as_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _part_xy(parts: dict[str, Any], key: str) -> tuple[float, float] | None:
    part = parts.get(key)
    if not isinstance(part, dict):
        return None
    price = _as_float(part.get("price"))
    if price is None:
        return None
    idx = part.get("index")
    if idx is None:
        idx = _DEFAULT_PART_X_INDEX.get(key, 12)
    try:
        idx_f = float(idx)
    except (TypeError, ValueError):
        idx_f = float(_DEFAULT_PART_X_INDEX.get(key, 12))
    return idx_f, price


def _line_by_role(lines: list[dict[str, Any]], role: str) -> dict[str, Any] | None:
    for line in lines or []:
        if isinstance(line, dict) and line.get("role") == role:
            return line
    return None


def _structural_by_kind(
    lines: list[dict[str, Any]], kind: str
) -> dict[str, Any] | None:
    for line in lines or []:
        if isinstance(line, dict) and line.get("kind") == kind:
            return line
    return None


def _step_status(checklist: dict[str, Any], key: str) -> str:
    for step in (checklist.get("steps") or []):
        if isinstance(step, dict) and step.get("key") == key:
            return str(step.get("status") or "UNKNOWN").upper()
    return "UNKNOWN"


def _safety_text_block(diagnostics: dict[str, Any]) -> dict[str, Any]:
    decision = diagnostics.get("decision") or {}
    safety = diagnostics.get("safety") or {}
    rich = (diagnostics.get("draft") or {}).get("rich_draft") or {}
    return {
        "decision_level": decision.get("level"),
        "ready_allowed": safety.get("ready_allowed"),
        "dispatch_called": safety.get("dispatch_called"),
        "ready_eligible": rich.get("ready_eligible"),
        "p0_pass": rich.get("p0_pass"),
    }


# ---------------------------------------------------------------------------
# HTML (with inline SVG)
# ---------------------------------------------------------------------------
_SVG_W = 1000
_SVG_H = 540
_PAD_L, _PAD_R, _PAD_T, _PAD_B = 60, 80, 50, 40


def _svg_x_from_index(index: float, x_max_index: float) -> float:
    if x_max_index <= 0:
        x_max_index = 25.0
    inner = _SVG_W - _PAD_L - _PAD_R
    return _PAD_L + (index / x_max_index) * inner


def _svg_y_from_price(price: float, lo: float, hi: float) -> float:
    if hi <= lo:
        hi = lo + 1e-6
    inner = _SVG_H - _PAD_T - _PAD_B
    return _PAD_T + (hi - price) / (hi - lo) * inner


def _build_inline_svg(rich_draft: dict[str, Any]) -> str:
    pattern = rich_draft.get("pattern_levels_draft") or {}
    parts = pattern.get("parts") if isinstance(pattern.get("parts"), dict) else {}
    pattern_kind = str(pattern.get("pattern_kind") or "unknown")
    is_dt = pattern_kind == "possible_double_top" or "P1" in parts
    skeleton_keys = ["P1", "NL", "P2", "BR"] if is_dt else ["B1", "NL", "B2", "BR"]

    skeleton_pts: list[tuple[str, float, float]] = []
    for k in skeleton_keys:
        p = _part_xy(parts, k)
        if p is not None:
            skeleton_pts.append((k, p[0], p[1]))

    wave_lines = rich_draft.get("wave_derived_lines_draft") or []
    structural = (rich_draft.get("structural_lines_draft") or {}).get("lines") or []
    sr_zones = (
        (rich_draft.get("support_resistance_v2_draft") or {})
        .get("selected_level_zones_top5")
        or []
    )

    wnl = _line_by_role(wave_lines, "entry_confirmation_line")
    wsl = _line_by_role(wave_lines, "stop_candidate")
    wtp = _line_by_role(wave_lines, "target_candidate")
    snl = _structural_by_kind(structural, "structural_neckline")
    sil = _structural_by_kind(structural, "structural_invalidation")
    stp = _structural_by_kind(structural, "structural_target")
    stl = _structural_by_kind(structural, "structural_trendline")

    prices: list[float] = [y for _, _, y in skeleton_pts]
    for src in (wnl, wsl, wtp, snl, sil, stp):
        if src and (p := _as_float(src.get("price"))) is not None:
            prices.append(p)
    for z in sr_zones:
        if isinstance(z, dict):
            for k in ("price", "price_low", "price_high"):
                if (p := _as_float(z.get(k))) is not None:
                    prices.append(p)
    if not prices:
        prices = [0.99, 1.01]

    pad_p = max((max(prices) - min(prices)) * 0.2, abs(max(prices)) * 0.001, 1e-4)
    y_lo = min(prices) - pad_p
    y_hi = max(prices) + pad_p
    x_max = max((p[1] for p in skeleton_pts), default=25.0) + 5

    parts_svg: list[str] = []

    parts_svg.append(
        f'<rect x="0" y="0" width="{_SVG_W}" height="{_SVG_H}" '
        f'fill="{COLORS["panel"]}" stroke="{COLORS["grid"]}"/>'
    )

    # Grid lines (4 horizontal).
    for i in range(1, 5):
        y = _PAD_T + i * (_SVG_H - _PAD_T - _PAD_B) / 5
        parts_svg.append(
            f'<line x1="{_PAD_L}" y1="{y}" x2="{_SVG_W - _PAD_R}" y2="{y}" '
            f'stroke="{COLORS["grid"]}" stroke-width="0.5"/>'
        )

    # Y axis price ticks.
    for i in range(0, 6):
        price = y_lo + i * (y_hi - y_lo) / 5
        y = _svg_y_from_price(price, y_lo, y_hi)
        parts_svg.append(
            f'<text x="{_PAD_L - 8}" y="{y + 4}" text-anchor="end" '
            f'font-size="11" fill="{COLORS["muted"]}">{price:.4f}</text>'
        )

    # Rough S/R zones. The outer <g class="rr-sr-zone"> is emitted
    # unconditionally so the geometry class is discoverable even when
    # the fixture didn't produce any rough zones (common for short
    # OHLC samples).
    sr_rects: list[str] = []
    for z in sr_zones:
        if not isinstance(z, dict):
            continue
        lo = _as_float(z.get("price_low")) or _as_float(z.get("price"))
        hi = _as_float(z.get("price_high")) or _as_float(z.get("price"))
        if lo is None or hi is None:
            continue
        if hi < lo:
            lo, hi = hi, lo
        y_top = _svg_y_from_price(hi, y_lo, y_hi)
        y_bot = _svg_y_from_price(lo, y_lo, y_hi)
        sr_rects.append(
            f'<rect class="rr-sr-zone" x="{_PAD_L}" y="{y_top}" '
            f'width="{_SVG_W - _PAD_L - _PAD_R}" height="{max(2, y_bot - y_top)}" '
            f'fill="{COLORS["numeric"]}" fill-opacity="0.18"/>'
        )
    parts_svg.append(
        f'<g class="rr-sr-zone" data-count="{len(sr_rects)}">'
        + "".join(sr_rects)
        + "</g>"
    )

    # Horizontal price lines.
    def _hline(price: float | None, css_class: str, color: str, label: str) -> None:
        if price is None:
            return
        y = _svg_y_from_price(price, y_lo, y_hi)
        parts_svg.append(
            f'<line class="{css_class}" x1="{_PAD_L}" y1="{y}" '
            f'x2="{_SVG_W - _PAD_R}" y2="{y}" stroke="{color}" '
            f'stroke-width="2.2" stroke-dasharray="6,5"/>'
        )
        label_x = _SVG_W - _PAD_R + 4
        parts_svg.append(
            f'<text x="{label_x}" y="{y + 4}" font-size="11" fill="{color}" '
            f'font-weight="700">{_esc(label)}</text>'
        )

    _hline(
        _as_float((wnl or {}).get("price")) or _as_float((snl or {}).get("price")),
        "rr-wnl-line",
        COLORS["neckline"],
        "WNL_D1 / SNL_D1",
    )
    _hline(
        _as_float((wsl or {}).get("price")) or _as_float((sil or {}).get("price")),
        "rr-wsl-line",
        COLORS["stop"],
        "WSL_D1 / SIL_D1",
    )
    _hline(
        _as_float((wtp or {}).get("price")) or _as_float((stp or {}).get("price")),
        "rr-wtp-line",
        COLORS["target"],
        "WTP_D1 / STP_D1",
    )
    _hline(
        _as_float((snl or {}).get("price")),
        "rr-structural-neckline",
        COLORS["neckline"],
        "",
    )
    _hline(
        _as_float((sil or {}).get("price")),
        "rr-structural-invalidation",
        COLORS["stop"],
        "",
    )
    _hline(
        _as_float((stp or {}).get("price")),
        "rr-structural-target",
        COLORS["target"],
        "",
    )

    # Wave skeleton.
    if len(skeleton_pts) >= 2:
        pts = " ".join(
            f"{_svg_x_from_index(x, x_max):.1f},"
            f"{_svg_y_from_price(y, y_lo, y_hi):.1f}"
            for _, x, y in skeleton_pts
        )
        parts_svg.append(
            f'<polyline class="rr-wave-skeleton-line" points="{pts}" '
            f'fill="none" stroke="{COLORS["wave"]}" stroke-width="2.8"/>'
        )
        for label, x, y in skeleton_pts:
            cx = _svg_x_from_index(x, x_max)
            cy = _svg_y_from_price(y, y_lo, y_hi)
            parts_svg.append(
                f'<circle class="rr-pivot-dot" cx="{cx:.1f}" cy="{cy:.1f}" '
                f'r="6" fill="white" stroke="{COLORS["wave"]}" stroke-width="2.5"/>'
            )
            parts_svg.append(
                f'<text class="rr-pivot-label" x="{cx:.1f}" y="{cy - 12:.1f}" '
                f'text-anchor="middle" font-size="12" font-weight="700" '
                f'fill="{COLORS["wave"]}">{_esc(label)}</text>'
            )

    # Structural trendline (P1-P2 / B1-B2).
    if stl is not None and len(skeleton_pts) >= 3:
        keys_in_order = [k for k, _, _ in skeleton_pts]
        primary = ("P1", "P2") if "P1" in keys_in_order else ("B1", "B2")
        a = next(((x, y) for k, x, y in skeleton_pts if k == primary[0]), None)
        b = next(((x, y) for k, x, y in skeleton_pts if k == primary[1]), None)
        if a and b:
            x1 = _svg_x_from_index(a[0], x_max)
            y1 = _svg_y_from_price(a[1], y_lo, y_hi)
            x2 = _svg_x_from_index(b[0], x_max)
            y2 = _svg_y_from_price(b[1], y_lo, y_hi)
            parts_svg.append(
                f'<line class="rr-structural-trendline" x1="{x1:.1f}" y1="{y1:.1f}" '
                f'x2="{x2:.1f}" y2="{y2:.1f}" stroke="{COLORS["structure"]}" '
                f'stroke-width="2.2"/>'
            )
            mx = (x1 + x2) / 2
            my = (y1 + y2) / 2
            parts_svg.append(
                f'<text x="{mx:.1f}" y="{my - 6:.1f}" text-anchor="middle" '
                f'font-size="11" font-weight="700" fill="{COLORS["structure"]}">'
                f"STL_D1 {primary[0]}-{primary[1]}</text>"
            )

    # Safety watermark — large, low-contrast.
    parts_svg.append(
        '<text class="rr-safety-watermark" x="500" y="300" '
        f'text-anchor="middle" font-size="44" fill="{COLORS["block"]}" '
        f'fill-opacity="0.10" font-weight="800" '
        'transform="rotate(-12 500 300)">観測専用 / NOT READY</text>'
    )

    # placeholder if pattern is unknown.
    if not skeleton_pts:
        parts_svg.append(
            '<text x="500" y="280" text-anchor="middle" '
            f'font-size="20" fill="{COLORS["muted"]}">'
            "パターン未検出 (観測専用プレースホルダー)</text>"
        )

    inner_svg = "\n".join(parts_svg)
    return (
        f'<svg viewBox="0 0 {_SVG_W} {_SVG_H}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="王道判定画面">{inner_svg}</svg>'
    )


def _build_checklist_html(rich_draft: dict[str, Any]) -> str:
    checklist = rich_draft.get("royal_road_procedure_checklist_draft") or {}
    rows: list[str] = []
    for key, label in CHECKLIST_LABELS_JA:
        status = _step_status(checklist, key)
        status_ja = STATUS_JA.get(status, status)
        color = {
            "PASS": COLORS["ready"],
            "WAIT": COLORS["wait"],
            "WARN": "#d97706",
            "BLOCK": COLORS["block"],
            "UNKNOWN": COLORS["unknown"],
        }.get(status, COLORS["unknown"])
        rows.append(
            "<tr>"
            f"<th>{_esc(label)}</th>"
            f'<td style="color:{color};font-weight:700">{_esc(status_ja)}</td>'
            "</tr>"
        )
    return "<table>" + "\n".join(rows) + "</table>"


def _build_safety_summary_html(diagnostics: dict[str, Any]) -> str:
    s = _safety_text_block(diagnostics)
    rows = [
        ("判定", s["decision_level"] or "UNKNOWN"),
        ("READY許可", s["ready_allowed"]),
        ("通知実行", s["dispatch_called"]),
        ("rich_draft.ready_eligible", s["ready_eligible"]),
        ("rich_draft.p0_pass", s["p0_pass"]),
    ]
    body = "".join(
        f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>" for k, v in rows
    )
    return f"<table>{body}</table>"


def _build_visual_review_html(visual_review: dict[str, Any] | None) -> str:
    if not visual_review:
        return (
            '<p class="muted">画面レビュー未実施 (API無効)。'
            '本番で OPENAI_API_KEY / ANTHROPIC_API_KEY を設定すると評価されます。</p>'
        )
    providers = visual_review.get("providers") or {}
    if not providers:
        return '<p class="muted">画面レビュー結果なし。</p>'
    rows = []
    for name, label in (("openai", "OpenAI"), ("claude", "Claude")):
        r = providers.get(name) or {}
        rows.append(
            f"<tr><th>{_esc(label)}</th>"
            f"<td>判定: <b>{_esc(r.get('verdict', 'UNKNOWN'))}</b><br>"
            f"日本語UI: {_esc(r.get('language', 'UNKNOWN'))}<br>"
            f"線の見やすさ: {_esc(r.get('line_visibility', 'UNKNOWN'))}<br>"
            f"安全性表記: {_esc(r.get('safety_clarity', 'UNKNOWN'))}<br>"
            f"<span class='muted'>{_esc(r.get('summary_ja', ''))}</span></td></tr>"
        )
    combined = visual_review.get("combined_verdict") or "UNKNOWN"
    rows.append(
        f"<tr><th>総合判定</th><td><b>{_esc(combined)}</b></td></tr>"
    )
    return "<table>" + "\n".join(rows) + "</table>"


_DECISION_SCREEN_CSS = """
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont,
  "Noto Sans CJK JP", "Yu Gothic", "Meiryo", sans-serif;
  background: #f4f7fb; color: #172033; }
.rr-screen { max-width: 1200px; margin: 0 auto; padding: 18px; }
.rr-safety-header { background: #0f172a; color: white;
  padding: 16px 20px; border-radius: 14px; margin-bottom: 14px; }
.rr-safety-header h1 { font-size: 20px; margin: 0 0 4px; }
.rr-safety-header .sub { color: #cbd5e1; font-size: 12px; }
.rr-safety-banner { background: #dcfce7; color: #166534;
  font-weight: 700; padding: 12px 14px; border-radius: 10px;
  margin-bottom: 14px; font-size: 14px; }
.rr-main { display: grid; grid-template-columns: 2fr 1fr;
  gap: 14px; }
.rr-chart-panel, .rr-checklist-panel, .rr-ai-visual-review {
  background: white; border: 1px solid #dbe4f0; border-radius: 14px;
  padding: 14px; box-shadow: 0 6px 16px rgba(15, 23, 42, .04); }
.rr-chart-panel svg { width: 100%; height: auto; display: block; }
.rr-chart-panel h2, .rr-checklist-panel h2, .rr-ai-visual-review h2 {
  font-size: 15px; margin: 0 0 10px; }
.rr-ai-visual-review { margin-top: 14px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid #e5eaf2; padding: 7px 6px;
  text-align: left; vertical-align: top; }
th { color: #475569; width: 38%; font-weight: 600; }
.muted { color: #64748b; font-size: 12px; }
.rr-legend { font-size: 11px; color: #64748b; margin-top: 10px;
  line-height: 1.6; }
"""


def build_royal_road_decision_screen_html(
    *,
    rich_draft: dict[str, Any],
    diagnostics: dict[str, Any],
    review_summary: dict[str, Any] | None = None,
    visual_review: dict[str, Any] | None = None,
) -> str:
    feed = diagnostics.get("feed") or {}
    pattern = (rich_draft or {}).get("pattern_levels_draft") or {}
    pattern_kind = pattern.get("pattern_kind") or "unknown"

    svg = _build_inline_svg(rich_draft or {})
    checklist_html = _build_checklist_html(rich_draft or {})
    safety_html = _build_safety_summary_html(diagnostics or {})
    visual_html = _build_visual_review_html(visual_review)

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>MVP-1 王道判定プレビュー</title>
  <style>{_DECISION_SCREEN_CSS}</style>
</head>
<body>
  <div class="rr-screen">
    <header class="rr-safety-header">
      <h1>MVP-1 王道判定プレビュー</h1>
      <div class="sub">
        観測専用 / READY通知不可 / 売買未使用 / source=draft / ready_eligible=False
      </div>
    </header>

    <div class="rr-safety-banner">
      安全: 観測専用 / READY通知不可 / 売買未使用
    </div>

    <main class="rr-main">
      <section class="rr-chart-panel">
        <h2>下書きチャート ({_esc(feed.get("symbol", "-"))} {_esc(feed.get("timeframe", "-"))})</h2>
        {svg}
        <p class="rr-legend">
          パターン: {_esc(pattern_kind)} ｜
          WNL_D1 = ネックライン下書き ｜
          WSL_D1 = 波形崩れ下書き ｜
          WTP_D1 = 利確候補下書き ｜
          STL_D1 = 構造トレンドライン下書き ｜
          サポレジ帯は薄青。<br>
          ENTRY指示ではありません。本番READY判定には未使用。
        </p>
      </section>

      <aside class="rr-checklist-panel">
        <h2>王道手順チェック</h2>
        {checklist_html}
        <p class="muted">
          P0未達 / READY不可 / 観測専用。
          多くの段階は WAIT / 未確認 のままで設計通りです。
        </p>
        <h2 style="margin-top:14px">安全フラグ</h2>
        {safety_html}
      </aside>
    </main>

    <section class="rr-ai-visual-review">
      <h2>AI画面レビュー (画面の見やすさ評価のみ。売買判定ではありません)</h2>
      {visual_html}
    </section>
  </div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# PNG (matplotlib)
# ---------------------------------------------------------------------------
def _png_placeholder(out: Path, message: str) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000d49444154789c63f8cfc0c0c0000000050001a5f8b9ed0000000049"
            "454e44ae426082"
        )
    )
    return out


def render_royal_road_decision_screen_png(
    *,
    rich_draft: dict[str, Any],
    diagnostics: dict[str, Any],
    out_path: str | Path,
    visual_review: dict[str, Any] | None = None,
) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except Exception:
        return _png_placeholder(out, "matplotlib unavailable")

    try:
        from .font_resolver import configure_matplotlib_japanese_font

        configure_matplotlib_japanese_font()
    except Exception:
        pass

    try:
        return _draw_png(rich_draft or {}, diagnostics or {}, out, plt, GridSpec)
    except Exception:
        return _png_placeholder(out, "decision screen render failed")


def _draw_png(
    rich_draft: dict[str, Any],
    diagnostics: dict[str, Any],
    out: Path,
    plt: Any,
    GridSpec: Any,
) -> Path:
    pattern = rich_draft.get("pattern_levels_draft") or {}
    parts = pattern.get("parts") if isinstance(pattern.get("parts"), dict) else {}
    pattern_kind = str(pattern.get("pattern_kind") or "unknown")
    is_dt = pattern_kind == "possible_double_top" or "P1" in parts
    skeleton_keys = ["P1", "NL", "P2", "BR"] if is_dt else ["B1", "NL", "B2", "BR"]
    feed = diagnostics.get("feed") or {}

    skeleton_pts: list[tuple[str, float, float]] = []
    for k in skeleton_keys:
        p = _part_xy(parts, k)
        if p is not None:
            skeleton_pts.append((k, p[0], p[1]))

    wave_lines = rich_draft.get("wave_derived_lines_draft") or []
    structural = (rich_draft.get("structural_lines_draft") or {}).get("lines") or []
    sr_zones = (
        (rich_draft.get("support_resistance_v2_draft") or {})
        .get("selected_level_zones_top5")
        or []
    )

    wnl = _line_by_role(wave_lines, "entry_confirmation_line")
    wsl = _line_by_role(wave_lines, "stop_candidate")
    wtp = _line_by_role(wave_lines, "target_candidate")
    snl = _structural_by_kind(structural, "structural_neckline")
    sil = _structural_by_kind(structural, "structural_invalidation")
    stp = _structural_by_kind(structural, "structural_target")
    stl = _structural_by_kind(structural, "structural_trendline")

    prices: list[float] = [y for _, _, y in skeleton_pts]
    for src in (wnl, wsl, wtp, snl, sil, stp):
        if src and (p := _as_float(src.get("price"))) is not None:
            prices.append(p)
    for z in sr_zones:
        if isinstance(z, dict):
            for k in ("price", "price_low", "price_high"):
                if (p := _as_float(z.get(k))) is not None:
                    prices.append(p)
    if not prices:
        prices = [0.99, 1.01]

    pad_p = max((max(prices) - min(prices)) * 0.2, abs(max(prices)) * 0.001, 1e-4)
    y_lo = min(prices) - pad_p
    y_hi = max(prices) + pad_p
    x_max = max((p[1] for p in skeleton_pts), default=25.0) + 5

    fig = plt.figure(figsize=(14, 7.875), dpi=140)
    fig.patch.set_facecolor(COLORS["bg"])
    gs = GridSpec(
        2,
        2,
        height_ratios=[10, 1],
        width_ratios=[7, 3],
        hspace=0.05,
        wspace=0.05,
        left=0.04,
        right=0.98,
        top=0.92,
        bottom=0.04,
    )
    ax = fig.add_subplot(gs[0, 0])
    panel = fig.add_subplot(gs[0, 1])
    footer = fig.add_subplot(gs[1, :])

    ax.set_facecolor(COLORS["panel"])
    ax.set_xlim(0, x_max)
    ax.set_ylim(y_lo, y_hi)
    ax.grid(True, color=COLORS["grid"], linewidth=0.5, alpha=0.7)
    ax.set_xticks([])
    for spine in ax.spines.values():
        spine.set_color(COLORS["grid"])

    fig.suptitle(
        f"MVP-1 王道判定プレビュー / {feed.get('symbol', '-')} "
        f"{feed.get('timeframe', '-')} / pattern={pattern_kind}",
        fontsize=14,
        fontweight="bold",
        color=COLORS["text"],
        x=0.04,
        ha="left",
        y=0.97,
    )
    ax.text(
        0.99,
        1.02,
        "観測専用 / READY通知不可 / 売買未使用 / source=draft / "
        "ready_eligible=False",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        color=COLORS["block"],
        fontsize=10,
        fontweight="bold",
    )

    # SR zones.
    for z in sr_zones:
        if not isinstance(z, dict):
            continue
        lo = _as_float(z.get("price_low")) or _as_float(z.get("price"))
        hi = _as_float(z.get("price_high")) or _as_float(z.get("price"))
        if lo is None or hi is None:
            continue
        if hi < lo:
            lo, hi = hi, lo
        ax.axhspan(lo, hi, color=COLORS["numeric"], alpha=0.15, zorder=1)

    def _hline(price: float | None, color: str, label: str) -> None:
        if price is None:
            return
        ax.axhline(price, color=color, linestyle="--", linewidth=2.0, alpha=0.95)
        ax.text(
            0.5,
            price,
            label,
            transform=ax.get_yaxis_transform(),
            ha="left",
            va="center",
            color=color,
            fontsize=9,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=color, lw=1.2),
        )

    _hline(
        _as_float((wnl or {}).get("price")) or _as_float((snl or {}).get("price")),
        COLORS["neckline"],
        "WNL_D1 / SNL_D1",
    )
    _hline(
        _as_float((wsl or {}).get("price")) or _as_float((sil or {}).get("price")),
        COLORS["stop"],
        "WSL_D1 / SIL_D1",
    )
    _hline(
        _as_float((wtp or {}).get("price")) or _as_float((stp or {}).get("price")),
        COLORS["target"],
        "WTP_D1 / STP_D1",
    )

    if len(skeleton_pts) >= 2:
        xs = [p[1] for p in skeleton_pts]
        ys = [p[2] for p in skeleton_pts]
        ax.plot(
            xs,
            ys,
            color=COLORS["wave"],
            linewidth=2.8,
            marker="o",
            markersize=8,
            markerfacecolor="white",
            markeredgewidth=2,
            markeredgecolor=COLORS["wave"],
            zorder=4,
        )
        for label, x, y in skeleton_pts:
            ax.text(
                x,
                y,
                label,
                ha="center",
                va="bottom",
                color=COLORS["wave"],
                fontsize=10,
                fontweight="bold",
                bbox=dict(
                    boxstyle="round,pad=0.25",
                    fc="white",
                    ec=COLORS["wave"],
                    lw=1.2,
                ),
                zorder=5,
            )

    if stl is not None and len(skeleton_pts) >= 3:
        primary = ("P1", "P2") if is_dt else ("B1", "B2")
        a = next(((x, y) for k, x, y in skeleton_pts if k == primary[0]), None)
        b = next(((x, y) for k, x, y in skeleton_pts if k == primary[1]), None)
        if a and b:
            ax.plot(
                [a[0], b[0]],
                [a[1], b[1]],
                color=COLORS["structure"],
                linewidth=2.4,
                alpha=0.9,
                zorder=3,
            )
            ax.text(
                (a[0] + b[0]) / 2,
                (a[1] + b[1]) / 2,
                f"STL_D1 {primary[0]}-{primary[1]}",
                ha="center",
                va="bottom",
                color=COLORS["structure"],
                fontsize=9,
                fontweight="bold",
                bbox=dict(
                    boxstyle="round,pad=0.2",
                    fc="white",
                    ec=COLORS["structure"],
                    lw=1,
                ),
                zorder=5,
            )

    if not skeleton_pts:
        ax.text(
            0.5,
            0.5,
            "パターン未検出\n(観測専用プレースホルダー)",
            transform=ax.transAxes,
            ha="center",
            va="center",
            color=COLORS["muted"],
            fontsize=14,
        )

    # Right panel: checklist (Latin headings + Japanese labels rendered if a
    # CJK font is available; otherwise tofu — accepted by spec).
    panel.set_facecolor(COLORS["panel"])
    panel.set_xticks([])
    panel.set_yticks([])
    for spine in panel.spines.values():
        spine.set_color(COLORS["grid"])
    panel.text(
        0.05,
        0.97,
        "王道手順チェック",
        transform=panel.transAxes,
        ha="left",
        va="top",
        fontsize=12,
        fontweight="bold",
        color=COLORS["text"],
    )
    checklist = rich_draft.get("royal_road_procedure_checklist_draft") or {}
    y = 0.92
    for key, label in CHECKLIST_LABELS_JA:
        status = _step_status(checklist, key)
        status_ja = STATUS_JA.get(status, status)
        color = {
            "PASS": COLORS["ready"],
            "WAIT": COLORS["wait"],
            "WARN": "#d97706",
            "BLOCK": COLORS["block"],
            "UNKNOWN": COLORS["unknown"],
        }.get(status, COLORS["unknown"])
        panel.text(
            0.05,
            y,
            f"{label}",
            transform=panel.transAxes,
            ha="left",
            va="top",
            fontsize=9,
            color=COLORS["text"],
        )
        panel.text(
            0.97,
            y,
            status_ja,
            transform=panel.transAxes,
            ha="right",
            va="top",
            fontsize=9,
            color=color,
            fontweight="bold",
        )
        y -= 0.055

    panel.text(
        0.05,
        0.04,
        "P0未達 / READY不可 / 観測専用",
        transform=panel.transAxes,
        ha="left",
        va="bottom",
        fontsize=9,
        color=COLORS["muted"],
    )

    # Footer with safety summary in plain text.
    footer.set_xticks([])
    footer.set_yticks([])
    for spine in footer.spines.values():
        spine.set_visible(False)
    s = _safety_text_block(diagnostics)
    footer_text = (
        f"判定: {s['decision_level']}  |  "
        f"READY許可: {s['ready_allowed']}  |  "
        f"通知実行: {s['dispatch_called']}  |  "
        f"ready_eligible: {s['ready_eligible']}  |  "
        f"p0_pass: {s['p0_pass']}  |  "
        "観測専用 / NOT READY ELIGIBLE / 売買未使用"
    )
    footer.text(
        0.5,
        0.5,
        footer_text,
        transform=footer.transAxes,
        ha="center",
        va="center",
        fontsize=10,
        color=COLORS["muted"],
    )

    fig.savefig(out, dpi=140, facecolor=COLORS["bg"])
    plt.close(fig)
    return out


__all__ = [
    "build_royal_road_decision_screen_html",
    "render_royal_road_decision_screen_png",
    "CHECKLIST_LABELS_JA",
    "STATUS_JA",
    "COLORS",
]
