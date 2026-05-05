from __future__ import annotations

from datetime import datetime, timezone

from fx_monitor.live.candle import Candle, CandleSeries


def _c(ts: int, o: float, h: float, lo: float, c: float, v: float = 100.0) -> Candle:
    return Candle(
        t=datetime.fromtimestamp(ts, tz=timezone.utc),
        o=o,
        h=h,
        l=lo,
        c=c,
        v=v,
    )


def test_candle_well_formed_true_for_valid_ohlc():
    assert _c(0, 1.0, 1.2, 0.9, 1.1).is_well_formed()


def test_candle_well_formed_false_when_high_below_close():
    assert not _c(0, 1.0, 1.05, 0.9, 1.1).is_well_formed()


def test_candle_series_basic_accessors():
    s = CandleSeries.from_iter(
        "EURUSD=X",
        "M5",
        [_c(0, 1.0, 1.1, 0.9, 1.05), _c(300, 1.05, 1.15, 1.0, 1.10)],
    )
    assert s.n == 2
    assert s.closes() == [1.05, 1.10]
    assert s.highs() == [1.1, 1.15]
    assert s.lows() == [0.9, 1.0]


def test_candle_series_slice_returns_subseries():
    s = CandleSeries.from_iter(
        "EURUSD=X",
        "M5",
        [_c(i, 1.0, 1.1, 0.9, 1.05) for i in range(0, 1500, 300)],
    )
    sub = s.slice(1, 4)
    assert sub.n == 3
    assert sub.symbol == "EURUSD=X"
