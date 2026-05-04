"""Multi-scale pivot detection for the live layer.

Fixes the failure modes of the legacy single-scale, tie-rejecting
detector:

- Tie-tolerant (a candle whose high equals others within the window can
  still be the pivot — strict equality is no longer disqualifying).
- Multi-scale: micro / swing / major emitted from one pass.
- ATR-based minimum swing filter to suppress micro noise.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .candle import Candle

PivotKind = Literal["HIGH", "LOW"]
PivotScale = Literal["micro", "swing", "major"]


class PivotPointV2(BaseModel):
    """One detected pivot. Pure observation: no direction or pattern label."""

    index: int
    timestamp_utc: str  # ISO8601 of the underlying candle
    price: float
    kind: PivotKind
    scale: PivotScale
    strength: int


_DEFAULT_SCALES: tuple[tuple[int, int, PivotScale], ...] = (
    (2, 2, "micro"),
    (5, 5, "swing"),
    (10, 10, "major"),
)


_SCALE_RANK: dict[PivotScale, int] = {"micro": 0, "swing": 1, "major": 2}


def _is_local_max(values: list[float], i: int, left: int, right: int) -> bool:
    """Tie-tolerant local maximum check.

    A candle qualifies as a local max if its value is >= every other value
    in the window. The legacy detector required strict uniqueness, which
    silently dropped pivots whose neighbours tied the extreme.
    """
    target = values[i]
    for j in range(i - left, i + right + 1):
        if j == i:
            continue
        if values[j] > target:
            return False
    return True


def _is_local_min(values: list[float], i: int, left: int, right: int) -> bool:
    target = values[i]
    for j in range(i - left, i + right + 1):
        if j == i:
            continue
        if values[j] < target:
            return False
    return True


def detect_multi_scale_pivots(
    candles: list[Candle],
    *,
    atr_m5: float,
    scales: tuple[tuple[int, int, PivotScale], ...] = _DEFAULT_SCALES,
    min_swing_atr_ratio: float = 0.5,
    max_pivots: int | None = None,
) -> list[PivotPointV2]:
    """Detect pivots at multiple scales with ATR noise filter.

    ``min_swing_atr_ratio`` requires the pivot to differ from its window
    neighbours' opposite extreme by at least ``atr_m5 * ratio``. With
    ``atr_m5 == 0`` (e.g. ATR not yet computable) the filter is skipped.

    When the same ``(index, kind)`` is detected at multiple scales we keep
    the largest scale (information is monotonic — a major swing implicitly
    is also a swing/micro, but the largest label is the most informative).
    """
    n = len(candles)
    if n == 0:
        return []
    highs = [c.h for c in candles]
    lows = [c.l for c in candles]

    raw: dict[tuple[int, PivotKind], PivotPointV2] = {}

    for left, right, scale in scales:
        if n < left + right + 1:
            continue
        for i in range(left, n - right):
            window_min_low = min(lows[i - left : i + right + 1])
            window_max_high = max(highs[i - left : i + right + 1])

            if _is_local_max(highs, i, left, right):
                if atr_m5 > 0 and (highs[i] - window_min_low) < atr_m5 * min_swing_atr_ratio:
                    pass
                else:
                    candidate = PivotPointV2(
                        index=i,
                        timestamp_utc=candles[i].t.isoformat(),
                        price=highs[i],
                        kind="HIGH",
                        scale=scale,
                        strength=left + right,
                    )
                    key = (i, "HIGH")
                    existing = raw.get(key)
                    if existing is None or _SCALE_RANK[scale] > _SCALE_RANK[existing.scale]:
                        raw[key] = candidate

            if _is_local_min(lows, i, left, right):
                if atr_m5 > 0 and (window_max_high - lows[i]) < atr_m5 * min_swing_atr_ratio:
                    pass
                else:
                    candidate = PivotPointV2(
                        index=i,
                        timestamp_utc=candles[i].t.isoformat(),
                        price=lows[i],
                        kind="LOW",
                        scale=scale,
                        strength=left + right,
                    )
                    key = (i, "LOW")
                    existing = raw.get(key)
                    if existing is None or _SCALE_RANK[scale] > _SCALE_RANK[existing.scale]:
                        raw[key] = candidate

    pivots = sorted(raw.values(), key=lambda p: (p.index, p.kind))
    if max_pivots is not None and len(pivots) > max_pivots:
        pivots = pivots[-max_pivots:]
    return pivots


__all__ = ["PivotPointV2", "PivotKind", "PivotScale", "detect_multi_scale_pivots"]
