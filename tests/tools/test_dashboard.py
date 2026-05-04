from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fx_monitor.ai.decision_screen_spec_schema import (
    AiDecisionScreenSpec,
    ScreenLine,
    ScreenPoint,
)
from fx_monitor.corpus.schema import CorpusEntry, OutcomeLabel
from fx_monitor.corpus.store import JsonlVectorStore
from fx_monitor.live.market_pack_v2 import (
    AtrPack,
    MarketAnalysisPackV2,
    RangePack,
)
from fx_monitor.tools._paths import corpus_root
from fx_monitor.tools.dashboard import (
    generate_dashboard,
    render_entry_page,
    render_index,
)


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FX_MONITOR_ROOT", str(tmp_path))


def _entry(
    entry_id: str,
    *,
    asof: datetime,
    outcome_status: str = "WIN",
    final_status: str = "WAIT_BREAKOUT",
    side: str = "SELL",
    dissent: bool = False,
) -> CorpusEntry:
    pack = MarketAnalysisPackV2(
        symbol="EURUSD=X",
        asof_utc=asof,
        candles=[],
        pivots=[],
        atr=AtrPack(m5_14=0.001),
        recent_range=RangePack(high_24h=1.20, low_24h=1.09),
        current_price=1.10,
        session="OVERLAP",
    )
    spec = AiDecisionScreenSpec(
        provider="claude",
        symbol="EURUSD=X",
        timeframe="M5",
        side=side,  # type: ignore[arg-type]
        final_status=final_status,  # type: ignore[arg-type]
        points=[ScreenPoint(id="P1", label="P1", role="high", index=0, price=1.105)],
        lines=[
            ScreenLine(
                id="L1",
                label="WNL",
                kind="neckline",
                role="entry_trigger",
                price=1.10,
                anchor_points=["P1"],
            )
        ],
    )
    return CorpusEntry(
        entry_id=entry_id,
        asof_utc=asof,
        symbol="EURUSD=X",
        timeframe="M5",
        source="live_recorded",
        market_pack=pack,
        feature_vector=[0.0] * 8,
        judgement=spec,
        judgement_at_utc=asof,
        outcome=OutcomeLabel(  # type: ignore[arg-type]
            status=outcome_status,
            max_favorable_pip=15.0,
            max_adverse_pip=-5.0,
            bars_observed=60,
        ),
        user_dissent=dissent,
    )


def test_render_index_contains_safety_banner_and_recent_only():
    now = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    entries = [
        _entry("recent", asof=now - timedelta(days=2)),
        _entry("old", asof=now - timedelta(days=60)),
    ]
    html = render_index(entries, generated_at=now, days=30)
    assert "観測専用ダッシュボード" in html
    assert "READY 通知 / 自動売買" in html
    # Recent entry visible, old one filtered out by 30-day window.
    assert "recent" in html  # entry_id may be truncated but link is present
    assert "old" not in html


def test_render_index_empty_corpus_shows_placeholder():
    now = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    html = render_index([], generated_at=now, days=30)
    assert "コーパス未蓄積" in html


def test_render_entry_page_includes_spec_and_pack():
    now = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    e = _entry("e-detail", asof=now - timedelta(hours=5))
    html = render_entry_page(e, generated_at=now)
    assert "判定詳細" in html
    assert "WAIT_BREAKOUT" in html
    assert "ai_decision_screen_spec_v1" in html
    assert "current=1.10000" in html


def test_generate_dashboard_writes_files():
    now = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    store = JsonlVectorStore(corpus_root("default"))
    store.add(_entry("a", asof=now - timedelta(hours=1)))
    store.add(_entry("b", asof=now - timedelta(days=2), outcome_status="LOSE"))
    store.add(_entry("old", asof=now - timedelta(days=60)))

    info = generate_dashboard(days=30, now_utc=now)
    out_root = Path(info["output_root"])
    assert (out_root / "index.html").exists()
    # Recent entries get individual pages; the old one is skipped.
    assert (out_root / "entries" / "a.html").exists()
    assert (out_root / "entries" / "b.html").exists()
    assert not (out_root / "entries" / "old.html").exists()
    assert info["total_entries"] == 3
    assert info["entry_pages_written"] == 2


def test_render_index_dissent_badge_appears():
    now = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
    e = _entry("d1", asof=now - timedelta(hours=2), dissent=True)
    html = render_index([e], generated_at=now, days=30)
    assert "DISSENT" in html
