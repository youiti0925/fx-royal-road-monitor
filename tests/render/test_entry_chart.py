from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

from fx_monitor.ai.decision_screen_spec_schema import (
    AiDecisionScreenSpec,
    ScreenLine,
    ScreenPoint,
)
from fx_monitor.corpus.schema import CorpusEntry, OutcomeLabel
from fx_monitor.live.candle import Candle
from fx_monitor.live.market_pack_v2 import (
    AtrPack,
    MarketAnalysisPackV2,
    RangePack,
)
from fx_monitor.live.pivots_v2 import PivotPointV2
from fx_monitor.render.entry_chart import render_entry_chart_png


def _entry(with_pivots: bool = True) -> CorpusEntry:
    asof = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
    candles = [
        Candle(
            t=asof - timedelta(minutes=5 * (60 - i)),
            o=1.10 + 0.001 * i,
            h=1.105 + 0.001 * i,
            l=1.095 + 0.001 * i,
            c=1.10 + 0.001 * i,
            v=100.0,
        )
        for i in range(60)
    ]
    pivots = [
        PivotPointV2(
            index=20,
            timestamp_utc=candles[20].t.isoformat(),
            price=candles[20].h,
            kind="HIGH",
            scale="swing",
            strength=10,
        ),
        PivotPointV2(
            index=40,
            timestamp_utc=candles[40].t.isoformat(),
            price=candles[40].l,
            kind="LOW",
            scale="major",
            strength=20,
        ),
    ] if with_pivots else []
    pack = MarketAnalysisPackV2(
        symbol="EURUSD=X",
        asof_utc=asof,
        candles=candles,
        pivots=pivots,
        atr=AtrPack(m5_14=0.001),
        recent_range=RangePack(high_24h=1.20, low_24h=1.09),
        current_price=1.16,
        session="OVERLAP",
    )
    spec = AiDecisionScreenSpec(
        provider="claude",
        symbol="EURUSD=X",
        timeframe="M5",
        side="SELL",
        final_status="WAIT_BREAKOUT",
        points=[
            ScreenPoint(id="P1", label="P1", role="high", index=20, price=1.13),
        ],
        lines=[
            ScreenLine(
                id="L1", label="WNL", kind="neckline", role="entry_trigger",
                price=1.13, anchor_points=["P1"],
            )
        ],
    )
    return CorpusEntry(
        entry_id="render-test",
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


def test_render_entry_chart_writes_png(tmp_path: Path):
    out = tmp_path / "chart.png"
    render_entry_chart_png(_entry(), out_path=out)
    assert out.exists()
    # PNG magic bytes
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_entry_chart_with_future_candles(tmp_path: Path):
    out = tmp_path / "chart_future.png"
    asof = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)
    future = [
        Candle(
            t=asof + timedelta(minutes=5 * (i + 1)),
            o=1.16 - 0.001 * i,
            h=1.165 - 0.001 * i,
            l=1.155 - 0.001 * i,
            c=1.16 - 0.001 * i,
            v=100.0,
        )
        for i in range(30)
    ]
    render_entry_chart_png(_entry(), out_path=out, future_candles=future)
    assert out.exists()
    # Image with future candles should be measurably bigger than minimum.
    assert out.stat().st_size > 5000


def test_render_entry_chart_handles_no_pivots(tmp_path: Path):
    out = tmp_path / "chart_no_pivots.png"
    render_entry_chart_png(_entry(with_pivots=False), out_path=out)
    assert out.exists()
