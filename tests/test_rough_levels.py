from __future__ import annotations

from datetime import datetime, timezone

from fx_monitor.analysis.rough_levels import build_rough_support_resistance
from fx_monitor.core.models import PivotPoint


def test_build_rough_support_resistance_groups_repeated_lows():
    ts = datetime.now(timezone.utc)
    pivots = [
        PivotPoint(index=1, timestamp_utc=ts, price=1.1000, kind="LOW"),
        PivotPoint(index=3, timestamp_utc=ts, price=1.1001, kind="LOW"),
        PivotPoint(index=5, timestamp_utc=ts, price=1.1050, kind="HIGH"),
    ]
    sr = build_rough_support_resistance(pivots, bucket_size=0.001)
    zones = sr["selected_level_zones_top5"]
    assert zones
    assert zones[0]["kind"] in ("support", "mixed")
    assert zones[0]["touch_count"] >= 2


def test_build_rough_support_resistance_empty_pivots():
    sr = build_rough_support_resistance([])
    assert sr["selected_level_zones_top5"] == []
    assert "no_pivots" in sr["warnings"]


def test_build_rough_support_resistance_sorted_by_touch_count():
    ts = datetime.now(timezone.utc)
    pivots = [
        PivotPoint(index=1, timestamp_utc=ts, price=1.0, kind="LOW"),
        PivotPoint(index=2, timestamp_utc=ts, price=1.0, kind="LOW"),
        PivotPoint(index=3, timestamp_utc=ts, price=2.0, kind="HIGH"),
        PivotPoint(index=4, timestamp_utc=ts, price=2.0, kind="HIGH"),
        PivotPoint(index=5, timestamp_utc=ts, price=2.0, kind="HIGH"),
    ]
    sr = build_rough_support_resistance(pivots, bucket_size=0.1)
    zones = sr["selected_level_zones_top5"]
    assert len(zones) == 2
    assert zones[0]["touch_count"] >= zones[1]["touch_count"]
