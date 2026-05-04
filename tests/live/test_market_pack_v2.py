from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fx_monitor.live.candle import Candle
from fx_monitor.live.market_pack_v2 import (
    MarketAnalysisPackV2,
    _classify_session,
    build_market_pack_v2,
)
from fx_monitor.live.pivots_v2 import detect_multi_scale_pivots


def _c(i: int, h: float, lo: float) -> Candle:
    return Candle(
        t=datetime.fromtimestamp(i * 300, tz=timezone.utc),
        o=(h + lo) / 2,
        h=h,
        l=lo,
        c=(h + lo) / 2,
        v=100.0,
    )


def test_session_classification_covers_all_buckets():
    # London-NY overlap window
    assert _classify_session(datetime(2026, 5, 4, 13, 0, tzinfo=timezone.utc)) == "OVERLAP"
    assert _classify_session(datetime(2026, 5, 4, 8, 0, tzinfo=timezone.utc)) == "LONDON"
    assert _classify_session(datetime(2026, 5, 4, 18, 0, tzinfo=timezone.utc)) == "NY"
    assert _classify_session(datetime(2026, 5, 4, 1, 0, tzinfo=timezone.utc)) == "TOKYO"
    assert _classify_session(datetime(2026, 5, 4, 22, 0, tzinfo=timezone.utc)) == "QUIET"


def test_build_pack_assembles_expected_structure():
    cs = [_c(i, 1.10 + 0.001 * i, 1.09 + 0.001 * i) for i in range(30)]
    pack = build_market_pack_v2(
        symbol="EURUSD=X",
        asof_utc=datetime(2026, 5, 4, 13, 0, tzinfo=timezone.utc),
        candles=cs,
        pivots=detect_multi_scale_pivots(cs, atr_m5=0.0),
        atr_m5_14=0.0008,
        high_24h=1.13,
        low_24h=1.09,
        current_price=1.115,
    )
    assert pack.schema_version == "market_analysis_pack_v2"
    assert pack.symbol == "EURUSD=X"
    assert pack.session == "OVERLAP"
    assert pack.recent_range.high_24h == 1.13


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "pattern_kind",
        "wave_derived_lines_draft",
        "structural_lines_draft",
        "trendline_context_draft",
        "royal_road_procedure_checklist_draft",
        "neckline_price",
    ],
)
def test_pack_schema_excludes_pollution_keys(forbidden_key: str):
    """The v2 pack must never expose code-derived judgement fields.

    We assert against the JSON schema rather than the source so a future
    refactor can't sneak the field in via a base class.
    """
    schema = MarketAnalysisPackV2.model_json_schema()
    serialised = json.dumps(schema)
    assert forbidden_key not in serialised


def test_market_pack_module_source_excludes_pollution_keys():
    """Module source must not even mention these strings.

    The CI safety lint enforces this on the whole live/ tree, but pin a
    direct test so a developer running pytest locally also gets feedback.
    """
    src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "fx_monitor"
        / "live"
        / "market_pack_v2.py"
    ).read_text(encoding="utf-8")
    for token in (
        "pattern_kind",
        "wave_derived_lines_draft",
        "structural_lines_draft",
        "trendline_context_draft",
        "royal_road_procedure_checklist_draft",
    ):
        assert token not in src, f"market_pack_v2.py must not reference {token!r}"
