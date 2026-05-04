from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from fx_monitor.live.candle import Candle
from fx_monitor.live.embedding import VECTOR_DIM, chart_pack_to_vector
from fx_monitor.live.market_pack_v2 import (
    AtrPack,
    CalendarEvent,
    MarketAnalysisPackV2,
    RangePack,
)


def _candles(n: int) -> list[Candle]:
    return [
        Candle(
            t=datetime.fromtimestamp(i * 300, tz=timezone.utc),
            o=1.10 + 0.001 * i,
            h=1.105 + 0.001 * i,
            l=1.095 + 0.001 * i,
            c=1.10 + 0.001 * i,
            v=100.0 + i,
        )
        for i in range(n)
    ]


def _pack(candles: list[Candle], **overrides) -> MarketAnalysisPackV2:
    base = dict(
        symbol="EURUSD=X",
        asof_utc=datetime(2026, 5, 4, 13, 0, tzinfo=timezone.utc),
        candles=candles,
        pivots=[],
        atr=AtrPack(m5_14=0.001, h1_14=0.002, h4_14=0.004),
        recent_range=RangePack(high_24h=1.20, low_24h=1.09),
        calendar_events_within_60min=[],
        current_price=1.12,
        current_spread=0.00005,
        session="OVERLAP",
    )
    base.update(overrides)
    return MarketAnalysisPackV2(**base)


def test_vector_has_fixed_length():
    pack = _pack(_candles(60))
    v = chart_pack_to_vector(pack)
    assert v.shape == (VECTOR_DIM,)
    assert v.dtype == np.float64


def test_vector_handles_short_candle_history():
    pack = _pack(_candles(5))
    v = chart_pack_to_vector(pack)
    assert v.shape == (VECTOR_DIM,)
    # Trailing candle slots should remain zero — embedding must not crash.
    assert np.all(v[5 * 4 : 240] == 0.0)


def test_vector_session_one_hot_set():
    pack = _pack(_candles(60), session="LONDON")
    v = chart_pack_to_vector(pack)
    # Session block starts at 240+16+4 = 260.
    base = 260
    london_idx = ("TOKYO", "LONDON", "NY", "OVERLAP", "QUIET").index("LONDON")
    assert v[base + london_idx] == 1.0
    # Only one bucket should be hot.
    assert v[base : base + 5].sum() == pytest.approx(1.0)


def test_vector_calendar_block_records_high_event():
    cal = [CalendarEvent(name="NFP", impact="HIGH", minutes_until=15)]
    pack = _pack(_candles(60), calendar_events_within_60min=cal)
    v = chart_pack_to_vector(pack)
    base = 260 + 5
    assert v[base + 2] == 1.0  # high count
    assert v[base + 3] == 15.0  # next high minutes


def test_vector_zero_atr_does_not_divide_by_zero():
    pack = _pack(_candles(60), atr=AtrPack(m5_14=0.0))
    v = chart_pack_to_vector(pack)
    assert np.all(np.isfinite(v))
