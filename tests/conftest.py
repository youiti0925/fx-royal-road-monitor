from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fx_monitor.core.models import (
    CalendarInfo,
    ChartPayload,
    HtfContext,
    LtfContext,
    TriggerInfo,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def passing_payload() -> ChartPayload:
    return ChartPayload(
        symbol="USDJPY",
        timeframe="M5",
        timestamp_utc=datetime(2026, 5, 3, 13, 55, tzinfo=timezone.utc),
        htf=HtfContext(h4_trend="up", d1_trend="up", key_levels=[155.20, 154.80]),
        ltf=LtfContext(
            structure="HH-HL",
            last_swing_high=155.10,
            last_swing_low=154.90,
            atr_14=0.12,
        ),
        trigger=TriggerInfo(type="breakout", occurred=True),
        calendar=CalendarInfo(high_impact_within_15min=False),
    )


@pytest.fixture
def ready_payload() -> dict:
    return json.loads(
        (FIXTURES / "royal_road_ready_sell_payload.json").read_text(encoding="utf-8")
    )
