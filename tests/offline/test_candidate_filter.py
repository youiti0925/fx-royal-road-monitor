from __future__ import annotations

from datetime import datetime, timezone

from fx_monitor.live.candle import Candle
from fx_monitor.offline.candidate_filter import is_candidate


def _candles(prices: list[tuple[float, float]]) -> list[Candle]:
    out = []
    for i, (lo, hi) in enumerate(prices):
        mid = (lo + hi) / 2
        out.append(
            Candle(
                t=datetime.fromtimestamp(i * 300, tz=timezone.utc),
                o=mid,
                h=hi,
                l=lo,
                c=mid,
                v=100.0,
            )
        )
    return out


def test_too_short_window_rejected():
    cs = _candles([(1.0, 1.01)] * 10)
    decision = is_candidate(cs)
    assert decision.is_candidate is False
    assert "window_too_short" in decision.reasons


def test_flat_window_rejected():
    # 60 candles of identical range -> ATR > 0 but no swing -> reject.
    cs = _candles([(1.000, 1.001)] * 60)
    decision = is_candidate(cs)
    assert decision.is_candidate is False


def test_strong_range_window_accepted():
    # Build a window with one clear swing + meaningful range.
    prices = (
        [(1.000, 1.001)] * 20
        + [(1.000, 1.030)] * 5
        + [(1.020, 1.030)] * 10
        + [(0.990, 1.020)] * 5
        + [(0.990, 1.000)] * 20
    )
    cs = _candles(prices)
    decision = is_candidate(cs)
    assert decision.is_candidate is True
    assert decision.reasons
