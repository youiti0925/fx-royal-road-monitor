"""Chart card renderer.

Produces a small PNG that summarizes the current setup. Matplotlib is an
optional dependency (`pip install -e .[chart]`); when it's missing we still
return a placeholder so the rest of the pipeline isn't blocked.
"""

from __future__ import annotations

from pathlib import Path

from ..core.models import ChartPayload


def render_chart_card(payload: ChartPayload, out_path: str | Path) -> Path:
    """Render a chart card PNG. Falls back to an empty placeholder file."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        # No matplotlib installed; write a tiny placeholder so callers can
        # still attach *something* (or just skip attaching).
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


__all__ = ["render_chart_card"]
