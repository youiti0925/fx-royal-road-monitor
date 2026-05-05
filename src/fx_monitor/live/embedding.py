"""Chart pack -> fixed-length feature vector.

The first version uses interpretable numeric features. We deliberately
avoid CLIP-like image embeddings for now: numeric features are
debuggable, fast, and need no GPU. The interface is stable so a richer
embedding can replace this implementation later without changing
callers.

Vector layout (272 dims total):

  [0..240)   Candle features: 60 bars x (h-c, l-c, c-prev_c, log1p_v)
             ATR-normalised so the vector is scale-free across symbols
             and regimes.
  [240..256) Top-4 swing/major pivot relative position + relative price
             (4 pivots x 4 dims = 16). Filled with zeros if fewer than 4
             eligible pivots are available.
  [256..260) ATR ratios: m5/m5, h1/m5, h4/m5, daily_range/m5.
  [260..265) Session one-hot (TOKYO/LONDON/NY/OVERLAP/QUIET).
  [265..269) Calendar event severity:
             [count_LOW, count_MED, count_HIGH, minutes_until_next_high]
  [269..270) Spread / atr_m5.
  [270..272) Reserved (currently zero-filled; preserved so vector
             length is 272 even as we extend.)
"""

from __future__ import annotations

import math

import numpy as np

from .market_pack_v2 import MarketAnalysisPackV2

VECTOR_DIM: int = 272

_CANDLE_BLOCK_SIZE: int = 240
_PIVOT_BLOCK_SIZE: int = 16
_ATR_BLOCK_SIZE: int = 4
_SESSION_BLOCK_SIZE: int = 5
_CALENDAR_BLOCK_SIZE: int = 4
_SPREAD_BLOCK_SIZE: int = 1
_RESERVED_BLOCK_SIZE: int = 2

_SESSIONS: tuple[str, ...] = ("TOKYO", "LONDON", "NY", "OVERLAP", "QUIET")

_CANDLES_REQUIRED: int = 60


def chart_pack_to_vector(pack: MarketAnalysisPackV2) -> np.ndarray:
    """Convert a MarketAnalysisPackV2 into a fixed-length numeric vector.

    The output is a length-:data:`VECTOR_DIM` ``float64`` numpy array.
    Missing data does not raise — slots are zero-filled — so the function
    is safe to call on cold-start packs that have shorter candle history
    or no calendar events.
    """
    out = np.zeros(VECTOR_DIM, dtype=np.float64)

    atr_m5 = pack.atr.m5_14 if pack.atr.m5_14 > 0 else 1e-9

    # ---- Candle block ----
    candles = pack.candles[-_CANDLES_REQUIRED:]
    base = 0
    prev_c: float | None = None
    for i, c in enumerate(candles):
        slot = base + i * 4
        out[slot + 0] = (c.h - c.c) / atr_m5
        out[slot + 1] = (c.l - c.c) / atr_m5
        out[slot + 2] = ((c.c - prev_c) / atr_m5) if prev_c is not None else 0.0
        out[slot + 3] = math.log1p(max(c.v or 0.0, 0.0))
        prev_c = c.c

    # ---- Pivot block ----
    base = _CANDLE_BLOCK_SIZE
    eligible = [p for p in pack.pivots if p.scale in ("swing", "major")]
    eligible = sorted(eligible, key=lambda p: p.index, reverse=True)[:4]
    eligible.reverse()
    last_index = len(pack.candles) - 1 if pack.candles else 0
    for j, p in enumerate(eligible):
        slot = base + j * 4
        rel_index = (p.index - last_index) / max(_CANDLES_REQUIRED, 1)
        rel_price = (p.price - pack.current_price) / atr_m5
        kind_sign = 1.0 if p.kind == "HIGH" else -1.0
        scale_weight = 1.0 if p.scale == "major" else 0.5
        out[slot + 0] = rel_index
        out[slot + 1] = rel_price
        out[slot + 2] = kind_sign
        out[slot + 3] = scale_weight

    # ---- ATR ratio block ----
    base = _CANDLE_BLOCK_SIZE + _PIVOT_BLOCK_SIZE
    out[base + 0] = 1.0
    out[base + 1] = (pack.atr.h1_14 / atr_m5) if pack.atr.h1_14 else 0.0
    out[base + 2] = (pack.atr.h4_14 / atr_m5) if pack.atr.h4_14 else 0.0
    daily_range = pack.recent_range.high_24h - pack.recent_range.low_24h
    out[base + 3] = daily_range / atr_m5

    # ---- Session one-hot ----
    base = _CANDLE_BLOCK_SIZE + _PIVOT_BLOCK_SIZE + _ATR_BLOCK_SIZE
    if pack.session in _SESSIONS:
        out[base + _SESSIONS.index(pack.session)] = 1.0

    # ---- Calendar block ----
    base = (
        _CANDLE_BLOCK_SIZE
        + _PIVOT_BLOCK_SIZE
        + _ATR_BLOCK_SIZE
        + _SESSION_BLOCK_SIZE
    )
    cnt_low = cnt_med = cnt_high = 0
    next_high_min: int | None = None
    for ev in pack.calendar_events_within_60min:
        if ev.impact == "LOW":
            cnt_low += 1
        elif ev.impact == "MEDIUM":
            cnt_med += 1
        elif ev.impact == "HIGH":
            cnt_high += 1
            if ev.minutes_until >= 0:
                if next_high_min is None or ev.minutes_until < next_high_min:
                    next_high_min = ev.minutes_until
    out[base + 0] = float(cnt_low)
    out[base + 1] = float(cnt_med)
    out[base + 2] = float(cnt_high)
    out[base + 3] = float(next_high_min) if next_high_min is not None else 60.0

    # ---- Spread / atr_m5 ----
    base = (
        _CANDLE_BLOCK_SIZE
        + _PIVOT_BLOCK_SIZE
        + _ATR_BLOCK_SIZE
        + _SESSION_BLOCK_SIZE
        + _CALENDAR_BLOCK_SIZE
    )
    out[base] = (pack.current_spread or 0.0) / atr_m5

    # Reserved bytes left at zero.
    return out


__all__ = ["VECTOR_DIM", "chart_pack_to_vector"]
