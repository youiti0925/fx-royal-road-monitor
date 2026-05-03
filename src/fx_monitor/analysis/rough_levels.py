"""Rough support/resistance from pivots.

Buckets nearby pivots into zones using a simple price grid. Output shape
mimics ``support_resistance_v2.selected_level_zones_top5`` from the
existing royal-road system so prompts and renderers can reuse the same key.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fx_monitor.core.models import PivotPoint


def build_rough_support_resistance(
    pivots: list[PivotPoint],
    *,
    bucket_size: float | None = None,
    max_zones: int = 5,
) -> dict[str, Any]:
    if not pivots:
        return {
            "schema_version": "rough_support_resistance_v1",
            "selected_level_zones_top5": [],
            "warnings": ["no_pivots"],
        }

    prices = [p.price for p in pivots]
    price_span = max(prices) - min(prices)
    if bucket_size is None:
        bucket_size = max(price_span / 30.0, abs(prices[-1]) * 0.0002, 0.0001)

    buckets: dict[int, list[PivotPoint]] = defaultdict(list)
    for p in pivots:
        key = int(round(p.price / bucket_size))
        buckets[key].append(p)

    zones: list[dict[str, Any]] = []
    for _, ps in buckets.items():
        if len(ps) < 2:
            continue
        zone_prices = [p.price for p in ps]
        kinds = {p.kind for p in ps}
        if kinds == {"LOW"}:
            kind = "support"
        elif kinds == {"HIGH"}:
            kind = "resistance"
        else:
            kind = "mixed"

        zones.append(
            {
                "id": f"RZ{len(zones) + 1}",
                "kind": kind,
                "price": sum(zone_prices) / len(zone_prices),
                "price_low": min(zone_prices),
                "price_high": max(zone_prices),
                "touch_count": len(ps),
                "source": "rough_pivots",
            }
        )

    zones.sort(key=lambda z: z["touch_count"], reverse=True)

    return {
        "schema_version": "rough_support_resistance_v1",
        "selected_level_zones_top5": zones[:max_zones],
        "warnings": [],
    }


__all__ = ["build_rough_support_resistance"]
