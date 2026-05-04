"""Phase P2: render an observation-only chart from ``rich_draft``.

The chart is built entirely from the rich-draft fields produced by
``fx_monitor.analysis.rich_draft.build_rich_draft``. It is intended for
human visual validation only and must never feed READY / notification /
trading paths. The image always carries a banner that reads:

    OBSERVATION ONLY - NOT READY ELIGIBLE

The renderer is defensive:

- Empty / unknown rich_draft -> a placeholder image is still produced.
- matplotlib missing            -> a tiny placeholder PNG is written.
- Any other exception           -> caught; placeholder PNG is written.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Re-use the existing renderer's color palette and small placeholder so
# the draft chart looks consistent with the production card.
from .chart_card_renderer import COLORS, _placeholder_png


_DEFAULT_PART_X = {"P1": 20.0, "B1": 20.0, "NL": 40.0, "P2": 60.0, "B2": 60.0, "BR": 78.0}


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
        x = _DEFAULT_PART_X.get(key, 50.0)
    try:
        x_f = float(x)
    except (TypeError, ValueError):
        x_f = _DEFAULT_PART_X.get(key, 50.0)
    return x_f, price


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


def render_draft_rich_chart(
    *,
    rich_draft: dict[str, Any] | None,
    out_path: str | Path,
    title: str = "Rich Draft Chart",
) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return _placeholder_png(out, "matplotlib unavailable for draft chart")

    try:
        from .font_resolver import configure_matplotlib_japanese_font

        configure_matplotlib_japanese_font()
    except Exception:
        pass

    try:
        return _draw(rich_draft or {}, out, title, plt)
    except Exception:
        # Belt-and-suspenders: a broken rich_draft must not bubble up to
        # the workflow. Write a placeholder so the artifact still exists.
        return _placeholder_png(out, "draft chart rendering failed")


def _draw(rich_draft: dict[str, Any], out: Path, title: str, plt) -> Path:
    pattern = rich_draft.get("pattern_levels_draft") or {}
    wave_lines = rich_draft.get("wave_derived_lines_draft") or []
    structural = (rich_draft.get("structural_lines_draft") or {}).get("lines") or []
    sr_zones = (
        (rich_draft.get("support_resistance_v2_draft") or {})
        .get("selected_level_zones_top5")
        or []
    )

    parts = pattern.get("parts") if isinstance(pattern.get("parts"), dict) else {}
    pattern_kind = str(pattern.get("pattern_kind") or "unknown")
    side = str(pattern.get("side") or "NEUTRAL")

    is_dt = pattern_kind == "possible_double_top" or "P1" in parts
    skeleton_keys = ["P1", "NL", "P2", "BR"] if is_dt else ["B1", "NL", "B2", "BR"]
    skeleton_pts: list[tuple[float, float]] = []
    for k in skeleton_keys:
        p = _part_xy(parts, k)
        if p is not None:
            skeleton_pts.append(p)

    wnl = _line_by_role(wave_lines, "entry_confirmation_line")
    wsl = _line_by_role(wave_lines, "stop_candidate")
    wtp = _line_by_role(wave_lines, "target_candidate")
    snl = _structural_by_kind(structural, "structural_neckline")
    sil = _structural_by_kind(structural, "structural_invalidation")
    stp = _structural_by_kind(structural, "structural_target")
    stl = _structural_by_kind(structural, "structural_trendline")

    wnl_price = _as_float(wnl.get("price")) if wnl else None
    wsl_price = _as_float(wsl.get("price")) if wsl else None
    wtp_price = _as_float(wtp.get("price")) if wtp else None
    snl_price = _as_float(snl.get("price")) if snl else None
    sil_price = _as_float(sil.get("price")) if sil else None
    stp_price = _as_float(stp.get("price")) if stp else None

    prices: list[float] = [y for _, y in skeleton_pts]
    for v in (wnl_price, wsl_price, wtp_price, snl_price, sil_price, stp_price):
        if v is not None:
            prices.append(v)
    for z in sr_zones:
        for k in ("price", "price_low", "price_high"):
            v = _as_float(z.get(k)) if isinstance(z, dict) else None
            if v is not None:
                prices.append(v)
    if not prices:
        prices = [0.99, 1.01]

    pad = max(
        (max(prices) - min(prices)) * 0.2,
        abs(max(prices)) * 0.001,
        0.0001,
    )
    y_lo = min(prices) - pad
    y_hi = max(prices) + pad

    fig, ax = plt.subplots(figsize=(11, 6.2), dpi=150)
    fig.patch.set_facecolor(COLORS["bg"])
    ax.set_facecolor(COLORS["panel"])
    ax.set_xlim(0, 100)
    ax.set_ylim(y_lo, y_hi)
    ax.grid(True, color=COLORS["grid"], linewidth=0.6, alpha=0.7)
    ax.set_xticks([])
    ax.tick_params(axis="y", colors=COLORS["muted"], labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(COLORS["grid"])

    # Header.
    header = f"{title}  /  {pattern_kind}  /  side={side}"
    ax.set_title(
        header, loc="left", color=COLORS["text"], fontsize=13, fontweight="bold", pad=10
    )

    # Big "OBSERVATION ONLY" banner so a screenshot can never be mistaken
    # for a tradeable signal.
    ax.text(
        0.99,
        1.02,
        "OBSERVATION ONLY  /  NOT READY ELIGIBLE  /  source=draft  /  ready_eligible=False",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        color=COLORS["block"],
        fontsize=10,
        fontweight="bold",
    )

    def _hline(price: float | None, color: str, label: str) -> None:
        if price is None:
            return
        ax.axhline(price, color=color, linestyle="--", linewidth=2.0, alpha=0.9)
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

    # Rough S/R zones (drawn first, low z).
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

    _hline(wnl_price or snl_price, COLORS["neckline"], "WNL_D1 / SNL_D1")
    _hline(wsl_price or sil_price, COLORS["stop"], "WSL_D1 / SIL_D1")
    _hline(wtp_price or stp_price, COLORS["target"], "WTP_D1 / STP_D1")

    # Wave skeleton.
    if len(skeleton_pts) >= 2:
        xs = [p[0] for p in skeleton_pts]
        ys = [p[1] for p in skeleton_pts]
        ax.plot(
            xs,
            ys,
            color=COLORS["wave"],
            linewidth=2.8,
            marker="o",
            markersize=8,
            markerfacecolor="white",
            markeredgewidth=2.0,
            markeredgecolor=COLORS["wave"],
            zorder=4,
        )
        for (x, y), key in zip(skeleton_pts, skeleton_keys[: len(skeleton_pts)]):
            ax.text(
                x,
                y,
                key,
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

    # Structural trendline STL_D1 connecting the two primary pivots.
    primary = ("P1", "P2") if is_dt else ("B1", "B2")
    p_a = _part_xy(parts, primary[0])
    p_b = _part_xy(parts, primary[1])
    if stl is not None and p_a is not None and p_b is not None:
        ax.plot(
            [p_a[0], p_b[0]],
            [p_a[1], p_b[1]],
            color=COLORS["structure"],
            linewidth=2.4,
            alpha=0.9,
            zorder=3,
        )
        ax.text(
            (p_a[0] + p_b[0]) / 2,
            (p_a[1] + p_b[1]) / 2,
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
                lw=1.0,
            ),
            zorder=5,
        )

    # If the rich_draft is empty we still produce a clear placeholder card.
    if not skeleton_pts and not wave_lines and not structural and not sr_zones:
        ax.text(
            0.5,
            0.5,
            "rich_draft empty\n(observation-only placeholder)",
            transform=ax.transAxes,
            ha="center",
            va="center",
            color=COLORS["muted"],
            fontsize=14,
        )

    # Footer reminder.
    ax.text(
        0.01,
        -0.06,
        "rich_draft schema = rich_royal_road_draft_v1   "
        "Not used for READY / notification / trading.",
        transform=ax.transAxes,
        ha="left",
        va="top",
        color=COLORS["muted"],
        fontsize=8,
    )

    fig.tight_layout()
    fig.savefig(out, dpi=150, facecolor=COLORS["bg"])
    plt.close(fig)
    return out


__all__ = ["render_draft_rich_chart"]
