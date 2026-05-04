from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fx_monitor.ai.decision_screen_spec_schema import AiDecisionScreenSpec
from fx_monitor.corpus.schema import CorpusEntry, OutcomeLabel
from fx_monitor.corpus.store import JsonlVectorStore
from fx_monitor.live.candle import Candle
from fx_monitor.live.market_pack_v2 import (
    AtrPack,
    MarketAnalysisPackV2,
    RangePack,
)
from fx_monitor.offline.outcome_filler import fill_pending_outcomes


def _entry(asof: datetime, *, side: str = "SELL", fs: str = "WAIT_BREAKOUT") -> CorpusEntry:
    pack = MarketAnalysisPackV2(
        symbol="EURUSD=X",
        asof_utc=asof,
        candles=[],
        pivots=[],
        atr=AtrPack(m5_14=0.001),
        recent_range=RangePack(high_24h=1.20, low_24h=1.09),
        current_price=1.10000,
        session="OVERLAP",
    )
    spec = AiDecisionScreenSpec(
        provider="claude",
        symbol="EURUSD=X",
        timeframe="M5",
        side=side,  # type: ignore[arg-type]
        final_status=fs,  # type: ignore[arg-type]
    )
    return CorpusEntry(
        entry_id=f"e-{asof.isoformat()}",
        asof_utc=asof,
        symbol="EURUSD=X",
        timeframe="M5",
        source="live_recorded",
        market_pack=pack,
        feature_vector=[0.0] * 8,
        judgement=spec,
        judgement_at_utc=asof,
        outcome=OutcomeLabel(status="PENDING"),
    )


def _make_future(prices: list[tuple[float, float]], start_at: datetime) -> list[Candle]:
    out = []
    for i, (lo, hi) in enumerate(prices):
        out.append(
            Candle(
                t=start_at + timedelta(minutes=5 * (i + 1)),
                o=(lo + hi) / 2,
                h=hi,
                l=lo,
                c=(lo + hi) / 2,
                v=100.0,
            )
        )
    return out


def test_fill_skips_recent_pending(tmp_path: Path):
    store = JsonlVectorStore(tmp_path / "corpus")
    now = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
    # Pending entry from 30 minutes ago — too recent for 60-bar M5 lookahead.
    store.add(_entry(now - timedelta(minutes=30)), skip_validation=True)

    def fetch_future(symbol: str, asof: datetime, n: int) -> list[Candle]:
        raise AssertionError("should not fetch when too recent")

    result = fill_pending_outcomes(
        store, fetch_future=fetch_future, lookahead_bars=60, now_utc=now
    )
    assert result.examined == 1
    assert result.filled == 0
    assert result.skipped_too_recent == 1


def test_fill_completes_when_age_sufficient(tmp_path: Path):
    store = JsonlVectorStore(tmp_path / "corpus")
    now = datetime(2026, 5, 4, 18, 0, tzinfo=timezone.utc)
    asof = now - timedelta(hours=10)  # plenty of age for 60 M5 bars
    store.add(_entry(asof), skip_validation=True)

    def fetch_future(symbol: str, asof_arg: datetime, n: int) -> list[Candle]:
        # 60 bars dropping 50 pip — favourable for a SELL judgement.
        prices = [(1.09950 - i * 0.00010, 1.10000 - i * 0.00010) for i in range(n)]
        return _make_future(prices, asof_arg)

    result = fill_pending_outcomes(
        store, fetch_future=fetch_future, lookahead_bars=60, now_utc=now
    )
    assert result.filled == 1
    assert result.skipped_too_recent == 0
    entry = store.all()[0]
    assert entry.outcome.status in ("WIN", "NEUTRAL_GOOD", "NEUTRAL_MISSED")


def test_fill_records_failure_when_fetch_returns_empty(tmp_path: Path):
    store = JsonlVectorStore(tmp_path / "corpus")
    now = datetime(2026, 5, 4, 18, 0, tzinfo=timezone.utc)
    asof = now - timedelta(hours=10)
    store.add(_entry(asof), skip_validation=True)

    def fetch_future(symbol: str, asof_arg: datetime, n: int) -> list[Candle]:
        return []

    result = fill_pending_outcomes(
        store, fetch_future=fetch_future, lookahead_bars=60, now_utc=now
    )
    assert result.filled == 0
    assert result.failed == 1
    # Entry should still be PENDING.
    assert store.all()[0].outcome.status == "PENDING"
