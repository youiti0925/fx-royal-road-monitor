"""Chart card renderer.

Two entry points:

- ``render_chart_card(payload, out_path)``: legacy, minimal placeholder card.
- ``render_royal_road_notification_card(...)``: the rich royal-road card used
  by the notifier. Driven entirely by the rich ``MonitorCase.ai_payload`` —
  no AI image generation, no synthetic OHLC. Every line, label, and marker
  on the chart is derived from the payload so the picture cannot disagree
  with the data fed to the AI reviewers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.models import (
    ChartPayload,
    CompareOutcome,
    MonitorCase,
    NotificationDecision,
    ReviewResult,
    RuleResult,
)


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
    "break": "#f97316",
    "retest": "#8b5cf6",
    "confirm": "#22c55e",
    "ready": "#16a34a",
    "wait": "#f59e0b",
    "block": "#ef4444",
    "unknown": "#94a3b8",
}


# ---------------------------------------------------------------------------
# Legacy minimal card (kept for backwards compatibility).
# ---------------------------------------------------------------------------
def render_chart_card(payload: ChartPayload, out_path: str | Path) -> Path:
    """Render a small chart card PNG. Falls back to an empty placeholder."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        out.write_bytes(b"")
        return out

    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.set_title(f"{payload.symbol} {payload.timeframe} @ {payload.timestamp_utc.isoformat()}")
    ax.axhline(payload.ltf.last_swing_high, linestyle="--", linewidth=1)
    ax.axhline(payload.ltf.last_swing_low, linestyle="--", linewidth=1)
    for lvl in payload.htf.key_levels:
        ax.axhline(lvl, linewidth=0.8, alpha=0.6)
    ax.text(
        0.02,
        0.95,
        f"h4={payload.htf.h4_trend} d1={payload.htf.d1_trend}\n"
        f"struct={payload.ltf.structure} atr={payload.ltf.atr_14:.4f}\n"
        f"trigger={payload.trigger.type} occurred={payload.trigger.occurred}",
        transform=ax.transAxes,
        verticalalignment="top",
        fontsize=9,
    )
    ax.set_yticks([])
    ax.set_xticks([])
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# Rich royal-road notification card.
# ---------------------------------------------------------------------------

# Default x positions for wave parts when the payload doesn't supply indices.
_DEFAULT_PART_X = {"P1": 20.0, "B1": 20.0, "NL": 40.0, "P2": 60.0, "B2": 60.0, "BR": 78.0}

_DISPLAY_STEP_KEYS: list[tuple[str, str]] = [
    ("wave_pattern", "波形"),
    ("neckline", "ネックライン"),
    ("breakout_confirmed", "ブレイク"),
    ("breakout", "ブレイク"),
    ("retest_confirmed", "リターンムーブ"),
    ("retest", "リターンムーブ"),
    ("confirmation_candle", "確認足"),
    ("entry_price", "ENTRY"),
    ("entry", "ENTRY"),
    ("stop_price", "STOP"),
    ("stop", "STOP"),
    ("target_price", "TP"),
    ("target", "TP"),
    ("rr_ok", "RR"),
    ("rr", "RR"),
    ("event_clear", "イベント"),
    ("event", "イベント"),
]


def _ai_payload(case: MonitorCase) -> dict[str, Any]:
    return case.ai_payload or {}


def _entry_plan(case: MonitorCase) -> dict[str, Any]:
    return _ai_payload(case).get("entry_plan") or {}


def _selected_candidate(case: MonitorCase) -> dict[str, Any]:
    return _ai_payload(case).get("selected_entry_candidate") or {}


def _pattern_levels(case: MonitorCase) -> dict[str, Any]:
    return _ai_payload(case).get("pattern_levels") or {}


def _structural_lines(case: MonitorCase) -> dict[str, Any]:
    return _ai_payload(case).get("structural_lines") or {}


def _wave_lines(case: MonitorCase) -> list[dict[str, Any]]:
    raw = _ai_payload(case).get("wave_derived_lines") or []
    return raw if isinstance(raw, list) else []


def _checklist(case: MonitorCase) -> dict[str, Any]:
    return _ai_payload(case).get("royal_road_procedure_checklist") or {}


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
    x = part.get("index")
    if x is None:
        x = part.get("idx")
    if x is None:
        x = _DEFAULT_PART_X.get(key, 50.0)
    try:
        x_f = float(x)
    except (TypeError, ValueError):
        x_f = _DEFAULT_PART_X.get(key, 50.0)
    return x_f, price


def _structural_line_by_kind(lines: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    for line in lines or []:
        if isinstance(line, dict) and line.get("kind") == kind:
            return line
    return None


def _wave_line_by_role(lines: list[dict[str, Any]], role: str) -> dict[str, Any] | None:
    for line in lines or []:
        if isinstance(line, dict) and line.get("role") == role:
            return line
    return None


def _verdict_color(verdict: str) -> str:
    v = (verdict or "").upper()
    if v in ("PASS", "READY"):
        return COLORS["ready"]
    if v in ("WAIT", "WATCH"):
        return COLORS["wait"]
    if v == "WARN":
        return "#d97706"
    if v in ("BLOCK", "SUPPRESSED"):
        return COLORS["block"]
    return COLORS["unknown"]


def _step_status(checklist: dict[str, Any], key: str) -> str:
    for s in checklist.get("steps") or []:
        if isinstance(s, dict) and s.get("key") == key:
            return str(s.get("status") or "UNKNOWN").upper()
    return ""


def _format_review_line(label: str, r: ReviewResult | None) -> tuple[str, str]:
    if r is None:
        return f"{label}: (not run)", COLORS["unknown"]
    text = f"{label}: {r.verdict} {r.bias} {r.confidence:.2f}"
    return text, _verdict_color(r.verdict)


def _conclusion(
    decision: NotificationDecision,
    case: MonitorCase,
    rule: RuleResult,
) -> str:
    level = decision.level
    if level == "READY":
        side = (_selected_candidate(case).get("side") or _entry_plan(case).get("side") or "").upper()
        side_word = "SELL" if side == "SELL" else ("BUY" if side == "BUY" else "")
        return f"WNLブレイク + リターンムーブ + 確認足 + RR成立で {side_word} READY".strip()
    if level == "SUPPRESSED":
        if "calendar" in decision.reason.lower() or rule.verdict == "BLOCK":
            return "イベント危険のため新規エントリー禁止"
        if "insufficient" in decision.reason.lower():
            return "AI二重判定が不成立のため通知抑制"
        if "cooldown" in decision.reason.lower():
            return "直近通知のクールダウン中のため抑制"
        return "通知抑制中"
    if level == "WATCH":
        return "観察継続 (READY条件は未充足)"
    if level == "INFO":
        return "観察ログ"
    return "未確定"


def _placeholder_png(out: Path, message: str) -> Path:
    """Write a tiny placeholder PNG when matplotlib isn't available."""
    out.parent.mkdir(parents=True, exist_ok=True)
    # Single-pixel PNG (gray) so callers always get a non-empty file.
    out.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000d49444154789c63f8cfc0c0c0000000050001a5f8b9ed0000000049"
            "454e44ae426082"
        )
    )
    return out


def render_royal_road_notification_card(
    *,
    case: MonitorCase,
    rule: RuleResult,
    openai_review: ReviewResult | None,
    claude_review: ReviewResult | None,
    compare_outcome: CompareOutcome,
    decision: NotificationDecision,
    out_path: str | Path,
) -> Path:
    """Render the rich royal-road notification card to PNG."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except Exception:
        return _placeholder_png(out, "matplotlib unavailable")

    ai = _ai_payload(case)
    ep = _entry_plan(case)
    sel = _selected_candidate(case)
    plv = _pattern_levels(case)
    sl = _structural_lines(case)
    wlines = _wave_lines(case)
    checklist = _checklist(case)

    parts = plv.get("parts") if isinstance(plv.get("parts"), dict) else {}
    pattern_kind = str(plv.get("pattern_kind") or "").lower()
    side = str(sel.get("side") or ep.get("side") or "").upper()

    is_dt = "double_top" in pattern_kind or side == "SELL" or "P1" in parts
    primary_keys = ("P1", "P2") if is_dt else ("B1", "B2")
    pattern_label = "DT" if is_dt else "DB"

    # ------------------------------ data prep ------------------------------
    skeleton_keys = [primary_keys[0], "NL", primary_keys[1], "BR"]
    skeleton_pts: list[tuple[float, float]] = []
    for k in skeleton_keys:
        p = _part_xy(parts, k)
        if p is not None:
            skeleton_pts.append(p)

    structural_line_objs = sl.get("lines") if isinstance(sl.get("lines"), list) else []

    # Neckline price: WNL > SNL > NL part > entry_price.
    wnl = _wave_line_by_role(wlines, "entry_confirmation_line")
    snl = _structural_line_by_kind(structural_line_objs, "structural_neckline")
    nl_part = _part_xy(parts, "NL")
    entry_price = _as_float(ep.get("entry_price"))
    neckline_price = (
        _as_float(wnl.get("price") if wnl else None)
        or _as_float(snl.get("price") if snl else None)
        or (nl_part[1] if nl_part else None)
        or entry_price
    )

    # Stop / target prices.
    wsl = _wave_line_by_role(wlines, "stop_candidate")
    sil = _structural_line_by_kind(structural_line_objs, "structural_invalidation")
    stop_price = (
        _as_float(ep.get("stop_price"))
        or _as_float(wsl.get("price") if wsl else None)
        or _as_float(sil.get("price") if sil else None)
    )

    wtp = _wave_line_by_role(wlines, "target_candidate")
    stp = _structural_line_by_kind(structural_line_objs, "structural_target")
    target_price = (
        _as_float(ep.get("target_price"))
        or _as_float(ep.get("target_extended_price"))
        or _as_float(wtp.get("price") if wtp else None)
        or _as_float(stp.get("price") if stp else None)
    )

    all_prices: list[float] = []
    for _, y in skeleton_pts:
        all_prices.append(y)
    for v in (neckline_price, stop_price, target_price, entry_price):
        if v is not None:
            all_prices.append(v)
    if not all_prices:
        all_prices = [0.9, 1.1]
    pad = max((max(all_prices) - min(all_prices)) * 0.2, abs(max(all_prices)) * 0.001, 0.0001)
    y_lo = min(all_prices) - pad
    y_hi = max(all_prices) + pad

    # ------------------------------ figure ------------------------------
    fig = plt.figure(figsize=(12, 6.75), dpi=160)
    fig.patch.set_facecolor(COLORS["bg"])
    gs = GridSpec(1, 2, width_ratios=[7, 3], wspace=0.05, left=0.04, right=0.98, top=0.94, bottom=0.06)
    ax = fig.add_subplot(gs[0, 0])
    panel = fig.add_subplot(gs[0, 1])

    ax.set_facecolor(COLORS["panel"])
    ax.set_xlim(0, 100)
    ax.set_ylim(y_lo, y_hi)
    ax.grid(True, color=COLORS["grid"], linewidth=0.6, alpha=0.7)
    ax.set_xticks([])
    ax.tick_params(axis="y", colors=COLORS["muted"], labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(COLORS["grid"])

    # Header
    symbol = case.chart_payload.symbol
    timeframe = case.chart_payload.timeframe
    status_word = (sel.get("status") or ep.get("entry_status") or "").upper()
    side_word = side or "-"
    header = f"{symbol} {timeframe}  /  {side_word}  /  {status_word or '-'}"
    ax.set_title(header, loc="left", color=COLORS["text"], fontsize=14, fontweight="bold", pad=10)
    ax.text(
        0.99, 1.02, f"{pattern_label}1  {pattern_kind or ''}".strip(),
        transform=ax.transAxes, ha="right", va="bottom",
        color=COLORS["wave"], fontsize=10, fontweight="bold",
    )

    # ----- horizontal lines (neckline / stop / target) -----
    def _hline(price: float, color: str, label: str) -> None:
        ax.axhline(price, color=color, linestyle="--", linewidth=2.2, alpha=0.95)
        ax.text(
            0.5, price, label,
            transform=ax.get_yaxis_transform(), ha="left", va="center",
            color=color, fontsize=10, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=color, lw=1.2),
        )

    if neckline_price is not None:
        _hline(neckline_price, COLORS["neckline"], "WNL / ENTRY / SNL1")
    if stop_price is not None:
        _hline(stop_price, COLORS["stop"], "WSL / STOP / SIL1")
    if target_price is not None:
        _hline(target_price, COLORS["target"], "WTP / TP / STP1")

    # ----- wave skeleton -----
    if len(skeleton_pts) >= 2:
        xs = [p[0] for p in skeleton_pts]
        ys = [p[1] for p in skeleton_pts]
        ax.plot(xs, ys, color=COLORS["wave"], linewidth=3.0, marker="o",
                markersize=9, markerfacecolor="white", markeredgewidth=2.5,
                markeredgecolor=COLORS["wave"], zorder=4)
        for (x, y), key in zip(skeleton_pts, skeleton_keys):
            ax.text(
                x, y, key,
                ha="center", va="bottom", color=COLORS["wave"],
                fontsize=10, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", fc="white",
                          ec=COLORS["wave"], lw=1.2),
                zorder=5,
            )

    # ----- structural trendline STL1 (P1-P2 or B1-B2) -----
    p_a = _part_xy(parts, primary_keys[0])
    p_b = _part_xy(parts, primary_keys[1])
    if p_a is not None and p_b is not None:
        ax.plot([p_a[0], p_b[0]], [p_a[1], p_b[1]],
                color=COLORS["structure"], linewidth=2.6, alpha=0.9, zorder=3)
        mx = (p_a[0] + p_b[0]) / 2
        my = (p_a[1] + p_b[1]) / 2
        ax.text(
            mx, my, f"STL1 {primary_keys[0]}-{primary_keys[1]}",
            ha="center", va="bottom", color=COLORS["structure"],
            fontsize=9, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", fc="white",
                      ec=COLORS["structure"], lw=1.0),
            zorder=5,
        )

    # ----- numeric trendline T1 (only if anchors present; we have none in fixture) -----
    tctx = ai.get("trendline_context") or {}
    tline = (tctx.get("selected_trendlines_top3") or [None])[0]
    if isinstance(tline, dict):
        ax1 = _as_float(tline.get("anchor_x1"))
        ay1 = _as_float(tline.get("anchor_y1"))
        ax2 = _as_float(tline.get("anchor_x2"))
        ay2 = _as_float(tline.get("anchor_y2"))
        if None not in (ax1, ay1, ax2, ay2):
            ax.plot([ax1, ax2], [ay1, ay2], color=COLORS["numeric"], linewidth=1.2, alpha=0.7, zorder=2)
            ax.text(ax2, ay2, "T1", color=COLORS["numeric"], fontsize=9, ha="left", va="bottom")

    # ----- BREAK / RETEST / CONFIRM markers -----
    br = _part_xy(parts, "BR")
    confirm = bool(ep.get("confirmation_candle"))
    is_break = bool(ep.get("breakout_confirmed"))
    is_retest = bool(ep.get("retest_confirmed"))
    nl_y = neckline_price if neckline_price is not None else (br[1] if br else None)

    # Anchor X reference for the post-break sequence.
    base_x = (br[0] if br else 78.0)

    def _marker(x: float, y: float, label: str, color: str, approx: bool) -> None:
        text = f"{label}~" if approx else label
        ax.scatter([x], [y], s=85, color=color, edgecolors="white", linewidths=1.5, zorder=6)
        ax.text(
            x, y, f"  {text}",
            color=color, fontsize=9, fontweight="bold",
            ha="left", va="center",
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=color, lw=1.0),
            zorder=7,
        )

    if is_break and br is not None:
        _marker(br[0], br[1], "BREAK", COLORS["break"], approx=False)
    if is_retest and nl_y is not None:
        _marker(min(base_x + 8, 95), nl_y, "RETEST", COLORS["retest"], approx=False)
    if confirm and nl_y is not None:
        offset = (y_hi - y_lo) * 0.04
        confirm_y = nl_y - offset if side == "SELL" else nl_y + offset
        _marker(min(base_x + 14, 98), confirm_y, "CONFIRM", COLORS["confirm"], approx=False)

    # ============================ right panel ============================
    panel.set_facecolor(COLORS["panel"])
    panel.set_xlim(0, 1)
    panel.set_ylim(0, 1)
    panel.set_xticks([])
    panel.set_yticks([])
    for spine in panel.spines.values():
        spine.set_color(COLORS["grid"])

    y_cursor = 0.97
    line_h = 0.045

    def _ptext(text: str, color: str, *, bold: bool = False, size: int = 10, indent: float = 0.05) -> None:
        nonlocal y_cursor
        panel.text(
            indent, y_cursor, text,
            color=color, fontsize=size,
            fontweight="bold" if bold else "normal",
            transform=panel.transAxes, va="top",
        )
        y_cursor -= line_h

    _ptext("3者判定", COLORS["text"], bold=True, size=12)
    rule_text = f"Rule: {rule.verdict} {rule.bias}"
    _ptext(rule_text, _verdict_color(rule.verdict), bold=True)
    o_text, o_color = _format_review_line("OpenAI", openai_review)
    _ptext(o_text, o_color)
    c_text, c_color = _format_review_line("Claude", claude_review)
    _ptext(c_text, c_color)
    _ptext(f"Compare: {compare_outcome.result}", _verdict_color(
        "PASS" if compare_outcome.result == "AGREE_PASS" else compare_outcome.result
    ))
    _ptext(f"Decision: {decision.level}", _verdict_color(decision.level), bold=True)

    y_cursor -= 0.015
    _ptext("王道手順チェック", COLORS["text"], bold=True, size=12)
    seen: set[str] = set()
    for key, label in _DISPLAY_STEP_KEYS:
        if label in seen:
            continue
        status = _step_status(checklist, key)
        if not status:
            continue
        seen.add(label)
        color = _verdict_color(status)
        _ptext(f"{label}: {status}", color)

    y_cursor -= 0.015
    _ptext("結論", COLORS["text"], bold=True, size=12)
    conclusion = _conclusion(decision, case, rule)
    # Wrap manually: the panel is narrow, so split on ~22 chars at a space.
    words = conclusion.split()
    line = ""
    for w in words:
        if len(line) + len(w) + 1 > 22 and line:
            _ptext(line, COLORS["text"])
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        _ptext(line, COLORS["text"])

    fig.savefig(out, dpi=160, facecolor=COLORS["bg"])
    plt.close(fig)
    return out


__all__ = [
    "render_chart_card",
    "render_royal_road_notification_card",
    "COLORS",
]
