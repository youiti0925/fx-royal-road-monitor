from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fx_monitor.ai.decision_screen_spec_schema import AiDecisionScreenSpec
from fx_monitor.corpus.outcome import compute_outcome
from fx_monitor.corpus.schema import CorpusEntry, OutcomeLabel
from fx_monitor.live.candle import Candle
from fx_monitor.live.market_pack_v2 import (
    AtrPack,
    MarketAnalysisPackV2,
    RangePack,
)


def _entry(final_status: str, side: str, base_price: float = 1.10000) -> CorpusEntry:
    pack = MarketAnalysisPackV2(
        symbol="EURUSD=X",
        asof_utc=datetime(2026, 5, 4, 13, 0, tzinfo=timezone.utc),
        candles=[],
        pivots=[],
        atr=AtrPack(m5_14=0.0008),
        recent_range=RangePack(high_24h=1.12, low_24h=1.08),
        current_price=base_price,
        session="OVERLAP",
    )
    spec = AiDecisionScreenSpec(
        provider="claude",
        symbol="EURUSD=X",
        timeframe="M5",
        side=side,  # type: ignore[arg-type]
        final_status=final_status,  # type: ignore[arg-type]
    )
    return CorpusEntry(
        entry_id="test-1",
        asof_utc=pack.asof_utc,
        symbol="EURUSD=X",
        timeframe="M5",
        source="live_recorded",
        market_pack=pack,
        feature_vector=[0.0] * 8,
        judgement=spec,
        judgement_at_utc=pack.asof_utc,
    )


def _candles(prices: list[tuple[float, float]]) -> list[Candle]:
    """Each tuple = (low, high). Open/close set to midpoint."""
    out: list[Candle] = []
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


def test_pending_when_no_future_candles():
    entry = _entry("WAIT_BREAKOUT", "SELL")
    out = compute_outcome(entry, [])
    assert out.status == "PENDING"
    assert out.bars_observed == 0


def test_wait_breakout_with_setup_completion_returns_win():
    entry = _entry("WAIT_BREAKOUT", "SELL", base_price=1.10000)
    # Drop 50 pip in argued direction -> setup played out -> WIN.
    future = _candles([(1.09950, 1.10000), (1.09500, 1.09800)])
    out = compute_outcome(entry, future)
    assert out.status == "WIN"
    assert out.max_favorable_pip is not None
    assert out.max_favorable_pip >= 30


def test_wait_breakout_with_against_movement_returns_lose():
    entry = _entry("WAIT_BREAKOUT", "SELL", base_price=1.10000)
    # Rise 25 pip against the argued SELL side -> setup invalidated -> LOSE.
    future = _candles([(1.10000, 1.10250), (1.10100, 1.10300)])
    out = compute_outcome(entry, future)
    assert out.status == "LOSE"


def test_wait_breakout_with_no_movement_is_good():
    entry = _entry("WAIT_BREAKOUT", "SELL", base_price=1.10000)
    # Tight chop, neither side reaches a meaningful threshold.
    future = _candles([(1.09995, 1.10005), (1.09990, 1.10010)])
    out = compute_outcome(entry, future)
    assert out.status == "NEUTRAL_GOOD"


def test_wait_breakout_with_modest_favourable_drift_is_neutral_missed():
    entry = _entry("WAIT_BREAKOUT", "SELL", base_price=1.10000)
    # Drop 20 pip — past wait_movement_pip (15) but short of ready_target_pip (30).
    future = _candles([(1.09800, 1.10000), (1.09800, 1.09900)])
    out = compute_outcome(entry, future)
    assert out.status == "NEUTRAL_MISSED"


def test_suppressed_judgement_with_quiet_market_is_win():
    entry = _entry("SUPPRESSED", "NEUTRAL", base_price=1.10000)
    future = _candles([(1.09995, 1.10005), (1.09990, 1.10010)])
    out = compute_outcome(entry, future)
    assert out.status == "WIN"


def test_suppressed_judgement_with_loud_market_is_lose():
    entry = _entry("SUPPRESSED", "NEUTRAL", base_price=1.10000)
    # 50 pip drop -> exceeds block_movement_pip default 30 -> LOSE.
    future = _candles([(1.09500, 1.10000), (1.09000, 1.09500)])
    out = compute_outcome(entry, future)
    assert out.status == "LOSE"


def test_outcome_caps_at_max_bars():
    entry = _entry("WAIT_BREAKOUT", "SELL", base_price=1.10000)
    future = _candles([(1.09995, 1.10005)] * 100)
    out = compute_outcome(entry, future, max_bars=20)
    assert out.bars_observed == 20
