from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fx_monitor.analysis.rich_draft import build_rich_draft
from fx_monitor.core.models import PivotPoint
from fx_monitor.render.draft_chart_renderer import render_draft_rich_chart

pytest.importorskip("matplotlib")


def _p(index: int, price: float, kind: str) -> PivotPoint:
    return PivotPoint(
        index=index,
        timestamp_utc=datetime(2026, 5, 4, tzinfo=timezone.utc),
        price=price,
        kind=kind,
        strength=2,
    )


def _dt_rich() -> dict:
    return build_rich_draft(
        pivots=[
            _p(1, 1.1050, "HIGH"),
            _p(2, 1.1000, "LOW"),
            _p(3, 1.1048, "HIGH"),
            _p(4, 1.0980, "LOW"),
        ],
        rough_support_resistance={
            "selected_level_zones_top5": [
                {"id": "RZ1", "price": 1.1000, "price_low": 1.0998, "price_high": 1.1002}
            ],
            "warnings": [],
        },
    )


def _db_rich() -> dict:
    return build_rich_draft(
        pivots=[
            _p(1, 1.0950, "LOW"),
            _p(2, 1.1000, "HIGH"),
            _p(3, 1.0952, "LOW"),
            _p(4, 1.1020, "HIGH"),
        ],
        rough_support_resistance={"selected_level_zones_top5": [], "warnings": []},
    )


def test_render_draft_rich_chart_double_top(tmp_path):
    out = tmp_path / "dt.png"
    path = render_draft_rich_chart(rich_draft=_dt_rich(), out_path=out)
    assert path.exists()
    assert path.stat().st_size > 5000


def test_render_draft_rich_chart_double_bottom(tmp_path):
    out = tmp_path / "db.png"
    path = render_draft_rich_chart(rich_draft=_db_rich(), out_path=out)
    assert path.exists()
    assert path.stat().st_size > 5000


def test_render_draft_rich_chart_empty_rich_draft(tmp_path):
    out = tmp_path / "empty.png"
    path = render_draft_rich_chart(rich_draft={}, out_path=out)
    assert path.exists()
    # Even the empty fallback produces a real PNG (placeholder text card),
    # not a 1-pixel placeholder.
    assert path.stat().st_size > 2000


def test_render_draft_rich_chart_creates_parent_dirs(tmp_path):
    out = tmp_path / "deep" / "nested" / "draft_chart.png"
    path = render_draft_rich_chart(rich_draft=_dt_rich(), out_path=out)
    assert path.exists()


def test_render_draft_rich_chart_handles_none(tmp_path):
    out = tmp_path / "none.png"
    path = render_draft_rich_chart(rich_draft=None, out_path=out)
    assert path.exists()
