from __future__ import annotations

from datetime import datetime, timezone

from fx_monitor.ai.decision_screen_spec_schema import (
    AiDecisionScreenSpec,
    ScreenLine,
    ScreenPoint,
)
from fx_monitor.live.candle import Candle
from fx_monitor.live.market_pack_v2 import (
    AtrPack,
    MarketAnalysisPackV2,
    RangePack,
)
from fx_monitor.live.post_validate import post_validate


def _pack() -> MarketAnalysisPackV2:
    candles = [
        Candle(
            t=datetime.fromtimestamp(i * 300, tz=timezone.utc),
            o=1.10 + 0.001 * i,
            h=1.105 + 0.001 * i,
            l=1.095 + 0.001 * i,
            c=1.10 + 0.001 * i,
            v=100.0,
        )
        for i in range(60)
    ]
    return MarketAnalysisPackV2(
        symbol="EURUSD=X",
        asof_utc=datetime(2026, 5, 4, 13, 0, tzinfo=timezone.utc),
        candles=candles,
        pivots=[],
        atr=AtrPack(m5_14=0.001),
        recent_range=RangePack(high_24h=1.20, low_24h=1.09),
        current_price=1.16,
        session="OVERLAP",
    )


def _spec(**overrides) -> AiDecisionScreenSpec:
    base = dict(
        provider="claude",
        symbol="EURUSD=X",
        timeframe="M5",
    )
    base.update(overrides)
    return AiDecisionScreenSpec(**base)


def test_clean_spec_passes_validation():
    pack = _pack()
    # A line right in the middle of the price range, anchored to a real point.
    spec = _spec(
        points=[ScreenPoint(id="P1", label="P1", role="high", index=20, price=1.12)],
        lines=[
            ScreenLine(
                id="L1",
                label="WNL",
                kind="neckline",
                role="entry_trigger",
                price=1.12,
                anchor_points=["P1"],
            )
        ],
    )
    result = post_validate(spec, pack)
    assert result.ok is True
    assert result.errors() == []
    assert result.downgraded is False


def test_line_far_outside_range_is_error():
    pack = _pack()
    spec = _spec(
        lines=[
            ScreenLine(
                id="L1",
                label="WNL",
                kind="neckline",
                role="entry_trigger",
                price=99.0,  # nowhere near reality
            )
        ],
    )
    result = post_validate(spec, pack)
    assert result.ok is False
    assert any(i.code == "line_out_of_range" for i in result.errors())
    assert result.downgraded is True


def test_anchor_not_touching_is_warning_not_error():
    pack = _pack()
    # Anchor at index 0, candle range ~1.095-1.105. Line at 1.15 is in
    # the overall pack price range (1.095-1.164) so coordinate check
    # passes, but the specific anchor candle is far from 1.15 -> warning.
    spec = _spec(
        points=[ScreenPoint(id="P1", label="P1", role="high", index=0, price=1.10)],
        lines=[
            ScreenLine(
                id="L1",
                label="WNL",
                kind="neckline",
                role="entry_trigger",
                price=1.15,
                anchor_points=["P1"],
            )
        ],
    )
    result = post_validate(spec, pack)
    assert result.ok is True  # warnings only, no error
    assert any(i.code == "line_not_touching_anchor" for i in result.warnings())


def test_point_index_out_of_bounds_is_error():
    pack = _pack()
    spec = _spec(
        points=[ScreenPoint(id="P1", label="P1", role="high", index=999, price=1.12)],
    )
    result = post_validate(spec, pack)
    assert any(i.code == "point_index_oob" for i in result.errors())


def test_safety_flag_flip_is_caught_at_layer3():
    """Even if the schema layer somehow let a flip through, Layer 3 still rejects."""
    pack = _pack()
    spec = _spec()
    # Bypass Pydantic validation by mutating after construction; this models
    # the worst case where some upstream code mutated the spec post-parse.
    object.__setattr__(spec, "used_for_ready", True)
    result = post_validate(spec, pack)
    assert any(i.code == "safety_flag_flipped" for i in result.errors())
    assert result.downgraded is True
