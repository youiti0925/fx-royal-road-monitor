"""Render a single AI-authored decision spec on top of the actual price chart.

Unlike :mod:`royal_road_decision_screen` (dual-AI, MVP1 era), this
renderer is for the v2 / $0 single-AI world. It paints what the AI
actually authored, plus what subsequently happened (when the outcome
is known). The caller passes a CorpusEntry; everything needed is on it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from fx_monitor.corpus.schema import CorpusEntry
from fx_monitor.live.candle import Candle


_CSS_BG = "#0b1220"
_CSS_PANEL = "#111a2c"
_CSS_GRID = "#1e293b"
_CSS_TEXT = "#e2e8f0"
_CSS_MUTED = "#94a3b8"
_CSS_BULL = "#22c55e"
_CSS_BEAR = "#ef4444"
_CSS_LINE_NECK = "#fbbf24"
_CSS_LINE_INVAL = "#ef4444"
_CSS_LINE_TARGET = "#22c55e"
_CSS_LINE_TREND = "#06b6d4"
_CSS_LINE_OTHER = "#a78bfa"
_CSS_PIVOT_HIGH = "#fbbf24"
_CSS_PIVOT_LOW = "#06b6d4"
_CSS_FUTURE = "#9ca3af"
_CSS_ZONE_FIB = "#f59e0b"      # amber: fibonacci prime zone
_CSS_ZONE_BUILDUP = "#a78bfa"  # violet: buildup consolidation
_CSS_ZONE_STOP_UP = "#ef4444"  # red: upper stop-zone (火薬庫)
_CSS_ZONE_STOP_DN = "#ef4444"
_CSS_ZONE_CONF = "#22c55e"     # green: triple-confluence point
_CSS_ZONE_GENERIC = "#64748b"  # slate: support/resistance/event/other


def _zone_style(kind: str) -> tuple[str, float, str | None]:
    """Return (color, alpha, hatch) for a zone kind."""
    if kind == "fibonacci_prime":
        return (_CSS_ZONE_FIB, 0.13, None)
    if kind == "buildup":
        return (_CSS_ZONE_BUILDUP, 0.16, "//")
    if kind == "stop_zone_upper":
        return (_CSS_ZONE_STOP_UP, 0.10, "xx")
    if kind == "stop_zone_lower":
        return (_CSS_ZONE_STOP_DN, 0.10, "xx")
    if kind == "confluence":
        return (_CSS_ZONE_CONF, 0.18, None)
    if kind in ("support", "resistance"):
        return (_CSS_ZONE_GENERIC, 0.10, None)
    return (_CSS_ZONE_GENERIC, 0.08, None)


def _line_color(kind: str) -> str:
    if kind == "neckline":
        return _CSS_LINE_NECK
    if kind == "invalidation":
        return _CSS_LINE_INVAL
    if kind == "target":
        return _CSS_LINE_TARGET
    if kind == "trendline":
        return _CSS_LINE_TREND
    return _CSS_LINE_OTHER


def render_entry_chart_png(
    entry: CorpusEntry,
    *,
    out_path: Path | str,
    future_candles: Sequence[Candle] | None = None,
    width_inches: float = 14.0,
    height_inches: float = 8.0,
) -> Path:
    """Render the entry as a PNG.

    Top panel: the 60-bar window the AI saw + AI lines/points overlaid +
    (if provided) the future candles in muted grey for outcome context.
    Bottom panel: the wave skeleton — pivots only, connected by light
    polyline so the structural story is readable at a glance.

    The function imports matplotlib lazily so the rest of the package
    stays importable without it.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec

        from .font_resolver import configure_matplotlib_japanese_font

        configure_matplotlib_japanese_font()
    except Exception:
        # Caller-friendly: write a tiny placeholder so the dashboard
        # always has *something* to embed even when matplotlib is absent.
        out.write_bytes(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f"
                "15c4890000000d49444154789c63f8cfc0c0c0000000050001a5f8b9ed00"
                "00000049454e44ae426082"
            )
        )
        return out

    pack = entry.market_pack
    spec = entry.judgement
    candles: list[Candle] = list(pack.candles)
    n_past = len(candles)
    future_list = list(future_candles or [])

    fig = plt.figure(figsize=(width_inches, height_inches), facecolor=_CSS_BG)
    gs = GridSpec(2, 1, height_ratios=[3, 1], hspace=0.18, figure=fig)
    ax_main = fig.add_subplot(gs[0, 0], facecolor=_CSS_PANEL)
    ax_skel = fig.add_subplot(gs[1, 0], facecolor=_CSS_PANEL)
    for ax in (ax_main, ax_skel):
        ax.tick_params(colors=_CSS_MUTED, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color(_CSS_GRID)
        ax.grid(True, color=_CSS_GRID, linewidth=0.5, alpha=0.5)

    # ---- Main panel: candles ----
    for i, c in enumerate(candles):
        colour = _CSS_BULL if c.c >= c.o else _CSS_BEAR
        ax_main.vlines(i, c.l, c.h, color=colour, linewidth=0.7, alpha=0.85)
        ax_main.add_patch(
            plt.Rectangle(  # type: ignore[attr-defined]
                (i - 0.3, min(c.o, c.c)),
                0.6,
                max(abs(c.c - c.o), 1e-7),
                facecolor=colour,
                edgecolor=colour,
                linewidth=0.5,
                alpha=0.9,
            )
        )

    # ---- Future candles (greyed) ----
    for j, c in enumerate(future_list):
        x = n_past + j
        ax_main.vlines(x, c.l, c.h, color=_CSS_FUTURE, linewidth=0.6, alpha=0.65)
        ax_main.add_patch(
            plt.Rectangle(  # type: ignore[attr-defined]
                (x - 0.3, min(c.o, c.c)),
                0.6,
                max(abs(c.c - c.o), 1e-7),
                facecolor=_CSS_FUTURE,
                edgecolor=_CSS_FUTURE,
                linewidth=0.4,
                alpha=0.55,
            )
        )

    x_max = n_past + max(len(future_list), 1)
    ax_main.set_xlim(-1, x_max)

    # ---- AI zones (fib prime / buildup / stop / confluence / generic) ----
    # Drawn FIRST so lines and points layer on top.
    for z in spec.zones:
        if z.price_low is None or z.price_high is None:
            continue
        color, alpha, hatch = _zone_style(z.kind)
        zx_lo = z.index_low if z.index_low is not None else 0
        zx_hi = z.index_high if z.index_high is not None else x_max - 1
        ax_main.add_patch(
            plt.Rectangle(
                (zx_lo, min(z.price_low, z.price_high)),
                max(zx_hi - zx_lo, 0.5),
                abs(z.price_high - z.price_low),
                facecolor=color, edgecolor=color,
                linewidth=0.8, alpha=alpha,
                hatch=hatch, zorder=1,
            )
        )
        # zone label at right edge of band, slightly outside
        label_y = (z.price_low + z.price_high) / 2
        ax_main.text(
            zx_hi + 0.3, label_y,
            f"{z.label}",
            color=color, fontsize=7, va="center",
            alpha=0.95,
        )

    # ---- AI lines ----
    point_by_id = {p.id: p for p in spec.points}
    for line in spec.lines:
        col = _line_color(line.kind)
        # Slanted line (trendline): use start_index/end_index/start_price/end_price.
        sx = getattr(line, "start_index", None)
        sx_p = getattr(line, "start_price", None)
        ex = getattr(line, "end_index", None)
        ex_p = getattr(line, "end_price", None)
        if sx is not None and ex is not None and sx_p is not None and ex_p is not None:
            ax_main.plot(
                [sx, ex], [sx_p, ex_p],
                color=col, linewidth=1.5, linestyle="--", alpha=0.9, zorder=4,
            )
            ax_main.text(
                ex + 0.3, ex_p,
                f"{line.label}",
                color=col, fontsize=8, va="center",
            )
            continue
        # Horizontal line at fixed price.
        if line.price is not None:
            x_lo = 0
            x_hi = x_max - 1
            if line.anchor_points:
                anchored_idx = [
                    point_by_id[a].index
                    for a in line.anchor_points
                    if a in point_by_id and point_by_id[a].index is not None
                ]
                if anchored_idx:
                    x_lo = max(0, min(anchored_idx) - 1)
                    x_hi = x_max - 1
            ax_main.hlines(
                line.price, x_lo, x_hi,
                colors=col, linewidth=1.3, linestyles="--", alpha=0.9,
            )
            ax_main.text(
                x_hi + 0.3, line.price,
                f"{line.label} ({line.price:.5f})",
                color=col, fontsize=8, va="center",
            )

    # ---- AI points ----
    for p in spec.points:
        if p.index is None or p.price is None:
            continue
        kind_col = _CSS_PIVOT_HIGH if p.role.endswith("high") or "high" in p.role.lower() else _CSS_PIVOT_LOW
        ax_main.scatter([p.index], [p.price], s=60, c=kind_col, edgecolors="white", linewidths=0.6, zorder=5)
        ax_main.annotate(
            f"{p.label}\n{p.price:.5f}",
            xy=(p.index, p.price),
            xytext=(0, 12 if "high" in p.role.lower() else -22),
            textcoords="offset points",
            color=kind_col, fontsize=8, ha="center",
        )

    # ---- ENTRY / STOP / TARGET / BREAKOUT prominent markers ----
    # Detect from existing lines and points so the visual cues are unmissable.
    # Marker is drawn at the right edge of the past window (idx n_past-1)
    # so it's clear "this is what the AI says".
    n_marker_x = max(n_past - 4, 0)

    side_arrow = "▼" if spec.side == "SELL" else ("▲" if spec.side == "BUY" else "◆")

    # ENTRY marker: scan lines for role=='entry_trigger', else use neckline.
    entry_line = next(
        (l for l in spec.lines if l.role == "entry_trigger" and l.price is not None),
        None,
    ) or next(
        (l for l in spec.lines if l.kind == "neckline" and l.price is not None),
        None,
    )
    if entry_line is not None:
        ax_main.scatter(
            [n_marker_x], [entry_line.price],
            s=320, c="#fbbf24", marker="*",
            edgecolors="white", linewidths=1.2, zorder=8,
        )
        ax_main.annotate(
            f" ENTRY {side_arrow} {entry_line.price:.5f}",
            xy=(n_marker_x, entry_line.price),
            xytext=(8, 0), textcoords="offset points",
            color="#fbbf24", fontsize=10, fontweight="bold", va="center", zorder=8,
            bbox=dict(boxstyle="round,pad=0.3", facecolor=_CSS_PANEL,
                      edgecolor="#fbbf24", linewidth=1.0, alpha=0.9),
        )

    # STOP marker: line.kind == 'invalidation'.
    stop_line = next(
        (l for l in spec.lines if l.kind == "invalidation" and l.price is not None),
        None,
    )
    if stop_line is not None:
        ax_main.scatter(
            [n_marker_x], [stop_line.price],
            s=220, c=_CSS_LINE_INVAL, marker="X",
            edgecolors="white", linewidths=1.2, zorder=8,
        )
        ax_main.annotate(
            f" STOP {stop_line.price:.5f}",
            xy=(n_marker_x, stop_line.price),
            xytext=(8, 0), textcoords="offset points",
            color=_CSS_LINE_INVAL, fontsize=10, fontweight="bold", va="center", zorder=8,
            bbox=dict(boxstyle="round,pad=0.3", facecolor=_CSS_PANEL,
                      edgecolor=_CSS_LINE_INVAL, linewidth=1.0, alpha=0.9),
        )

    # TARGET marker: line.kind == 'target'.
    target_line = next(
        (l for l in spec.lines if l.kind == "target" and l.price is not None),
        None,
    )
    if target_line is not None:
        ax_main.scatter(
            [n_marker_x], [target_line.price],
            s=240, c=_CSS_LINE_TARGET, marker="D",
            edgecolors="white", linewidths=1.2, zorder=8,
        )
        ax_main.annotate(
            f" TARGET {target_line.price:.5f}",
            xy=(n_marker_x, target_line.price),
            xytext=(8, 0), textcoords="offset points",
            color=_CSS_LINE_TARGET, fontsize=10, fontweight="bold", va="center", zorder=8,
            bbox=dict(boxstyle="round,pad=0.3", facecolor=_CSS_PANEL,
                      edgecolor=_CSS_LINE_TARGET, linewidth=1.0, alpha=0.9),
        )

    # BREAKOUT marker: scan points for role containing 'breakout'.
    breakout_pt = next(
        (p for p in spec.points
         if "breakout" in p.role.lower() and p.index is not None and p.price is not None),
        None,
    )
    if breakout_pt is not None:
        ax_main.scatter(
            [breakout_pt.index], [breakout_pt.price],
            s=260, c="#06b6d4", marker="P",
            edgecolors="white", linewidths=1.2, zorder=8,
        )
        ax_main.annotate(
            f"BREAK",
            xy=(breakout_pt.index, breakout_pt.price),
            xytext=(0, -28), textcoords="offset points",
            color="#06b6d4", fontsize=9, fontweight="bold", ha="center", zorder=8,
            bbox=dict(boxstyle="round,pad=0.2", facecolor=_CSS_PANEL,
                      edgecolor="#06b6d4", linewidth=1.0, alpha=0.9),
        )

    # Outcome marker at the boundary
    if future_list:
        ax_main.axvline(n_past - 0.5, color="#fbbf24", linewidth=1.0, alpha=0.6, linestyle=":")
        ax_main.text(
            n_past - 0.5, ax_main.get_ylim()[1],
            " 判定時点 →",
            color="#fbbf24", fontsize=9, va="top",
        )

    title_status = f"{spec.side} / {spec.final_status}"
    if entry.outcome.status != "PENDING":
        title_status += f"  →  {entry.outcome.status}"
    ax_main.set_title(
        f"{pack.symbol}  {pack.timeframe}  asof={pack.asof_utc.isoformat()}\n{title_status}",
        color=_CSS_TEXT, fontsize=11, loc="left",
    )

    # Prominent pattern banner inside the chart so the doctrine label is unmissable.
    # Place at left so it doesn't overlap with "判定時点 →" annotation on the right.
    if spec.pattern_label_ja:
        ax_main.text(
            0.02, 0.97,
            f"  {spec.pattern_label_ja}  ",
            transform=ax_main.transAxes,
            color=_CSS_TEXT, fontsize=10, ha="left", va="top",
            bbox=dict(
                boxstyle="round,pad=0.4",
                facecolor=_CSS_PANEL, edgecolor=_CSS_LINE_NECK,
                linewidth=1.2, alpha=0.92,
            ),
            zorder=10,
        )
    ax_main.set_ylabel("price", color=_CSS_MUTED, fontsize=9)

    # ---- Wave skeleton (bottom) ----
    pivots_sorted = sorted(pack.pivots, key=lambda p: p.index)
    if pivots_sorted:
        xs = [p.index for p in pivots_sorted]
        ys = [p.price for p in pivots_sorted]
        ax_skel.plot(xs, ys, color=_CSS_TEXT, alpha=0.7, linewidth=1.2)
        for p in pivots_sorted:
            col = _CSS_PIVOT_HIGH if p.kind == "HIGH" else _CSS_PIVOT_LOW
            sz = 18 if p.scale == "micro" else (40 if p.scale == "swing" else 70)
            ax_skel.scatter([p.index], [p.price], s=sz, c=col, edgecolors="white", linewidths=0.4, zorder=5)
    ax_skel.set_xlim(-1, x_max)
    ax_skel.set_title("波形スケルトン (pivot polyline)", color=_CSS_MUTED, fontsize=9, loc="left")
    ax_skel.set_xlabel("bar index", color=_CSS_MUTED, fontsize=9)

    # Safety watermark
    fig.text(
        0.99, 0.01,
        "観測専用 / READY通知不可 / 売買未使用",
        color=_CSS_MUTED, fontsize=8, ha="right",
    )

    fig.savefig(out, dpi=110, facecolor=_CSS_BG, bbox_inches="tight")
    plt.close(fig)
    return out


__all__ = ["render_entry_chart_png"]
