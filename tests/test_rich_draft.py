from __future__ import annotations

from datetime import datetime, timezone

from fx_monitor.analysis.rich_draft import build_rich_draft
from fx_monitor.core.models import PivotPoint


def _p(index: int, price: float, kind: str) -> PivotPoint:
    return PivotPoint(
        index=index,
        timestamp_utc=datetime(2026, 5, 4, tzinfo=timezone.utc),
        price=price,
        kind=kind,
        strength=2,
    )


def test_build_rich_draft_possible_double_top():
    pivots = [
        _p(1, 1.1050, "HIGH"),
        _p(2, 1.1000, "LOW"),
        _p(3, 1.1048, "HIGH"),
        _p(4, 1.0980, "LOW"),
    ]
    rough_sr = {
        "selected_level_zones_top5": [{"id": "RZ1", "price": 1.1000}],
        "warnings": [],
    }

    rich = build_rich_draft(pivots=pivots, rough_support_resistance=rough_sr)

    assert rich["observation_only"] is True
    assert rich["used_in_final_action"] is False
    assert rich["ready_eligible"] is False
    assert rich["pattern_levels_draft"]["pattern_kind"] == "possible_double_top"
    assert rich["pattern_levels_draft"]["side"] == "SELL"
    assert len(rich["wave_derived_lines_draft"]) == 3
    assert rich["structural_lines_draft"]["counts"]["total"] >= 4
    assert rich["royal_road_procedure_checklist_draft"]["p0_pass"] is False


def test_build_rich_draft_possible_double_bottom():
    pivots = [
        _p(1, 1.0950, "LOW"),
        _p(2, 1.1000, "HIGH"),
        _p(3, 1.0952, "LOW"),
        _p(4, 1.1020, "HIGH"),
    ]
    rough_sr = {"selected_level_zones_top5": [], "warnings": []}

    rich = build_rich_draft(pivots=pivots, rough_support_resistance=rough_sr)

    assert rich["pattern_levels_draft"]["pattern_kind"] == "possible_double_bottom"
    assert rich["pattern_levels_draft"]["side"] == "BUY"
    assert rich["pattern_levels_draft"]["parts"]["B1"]["price"] == 1.0950
    assert rich["pattern_levels_draft"]["parts"]["B2"]["price"] == 1.0952
    assert rich["ready_eligible"] is False


def test_build_rich_draft_insufficient_pivots_never_ready():
    rich = build_rich_draft(
        pivots=[],
        rough_support_resistance={"selected_level_zones_top5": [], "warnings": []},
    )

    assert rich["ready_eligible"] is False
    assert rich["pattern_levels_draft"]["available"] is False
    assert rich["wave_derived_lines_draft"] == []
    assert rich["royal_road_procedure_checklist_draft"]["p0_pass"] is False


def test_rich_draft_every_line_carries_observation_only():
    pivots = [
        _p(1, 1.1050, "HIGH"),
        _p(2, 1.1000, "LOW"),
        _p(3, 1.1048, "HIGH"),
        _p(4, 1.0980, "LOW"),
    ]
    rich = build_rich_draft(
        pivots=pivots,
        rough_support_resistance={"selected_level_zones_top5": [], "warnings": []},
    )

    for line in rich["wave_derived_lines_draft"]:
        assert line["source"] == "draft"
        assert line["observation_only"] is True
        assert line["used_in_final_action"] is False

    for line in rich["structural_lines_draft"]["lines"]:
        assert line["source"] == "draft"
        assert line["observation_only"] is True
        assert line["used_in_final_action"] is False


def test_rich_draft_keys_use_draft_suffix_and_dont_clobber_production():
    pivots = [_p(1, 1.10, "HIGH"), _p(2, 1.09, "LOW"), _p(3, 1.10, "HIGH"), _p(4, 1.085, "LOW")]
    rich = build_rich_draft(
        pivots=pivots,
        rough_support_resistance={"selected_level_zones_top5": [], "warnings": []},
    )

    expected = {
        "pattern_levels_draft",
        "wave_derived_lines_draft",
        "structural_lines_draft",
        "support_resistance_v2_draft",
        "trendline_context_draft",
        "royal_road_procedure_checklist_draft",
    }
    assert expected <= set(rich.keys())

    forbidden = {
        "pattern_levels",
        "wave_derived_lines",
        "structural_lines",
        "support_resistance_v2",
        "trendline_context",
        "royal_road_procedure_checklist",
    }
    assert forbidden.isdisjoint(set(rich.keys()))
