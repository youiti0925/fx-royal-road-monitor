"""Adapter: :class:`RoyalRoadDraftPayload` -> :class:`MonitorCase`.

Wraps the draft so it flows through the same pipeline as a real
:class:`MonitorCase`. The ``ai_payload`` carries ``observation_only=True``
so the rule engine's draft guard refuses to return PASS.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fx_monitor.core.models import (
    CalendarInfo,
    ChartPayload,
    HtfContext,
    LtfContext,
    MonitorCase,
    RoyalRoadDraftPayload,
    TriggerInfo,
)


def build_monitor_case_from_draft_payload(
    draft: RoyalRoadDraftPayload,
) -> MonitorCase:
    prices = [p.price for p in draft.pivots]
    if prices:
        high = max(prices)
        low = min(prices)
    else:
        high, low = 1.0, 0.9
    if high <= low:
        high = low + 0.0001

    chart_payload = ChartPayload(
        symbol=draft.symbol,
        timeframe=draft.timeframe,
        timestamp_utc=draft.timestamp_utc or datetime.now(tz=timezone.utc),
        htf=HtfContext(h4_trend="range", d1_trend="range", key_levels=[]),
        ltf=LtfContext(
            structure="range",
            last_swing_high=high,
            last_swing_low=low,
            atr_14=max((high - low) / 10.0, 0.0001),
        ),
        trigger=TriggerInfo(type="none", occurred=False),
        calendar=CalendarInfo(high_impact_within_15min=False),
    )

    rich = draft.rich_draft or {}
    ai_payload: dict[str, Any] = {
        "symbol": draft.symbol,
        "timeframe": draft.timeframe,
        "source": draft.source,
        "timestamp_utc": draft.timestamp_utc.isoformat() if draft.timestamp_utc else None,
        "observation_only": True,
        "used_in_final_action": False,
        "pivots": [p.model_dump(mode="json") for p in draft.pivots],
        "rough_support_resistance": draft.rough_support_resistance,
        "rough_wave_context": draft.rough_wave_context,
        "entry_plan": draft.entry_plan,
        "selected_entry_candidate": draft.selected_entry_candidate,
        "royal_road_procedure_checklist": draft.royal_road_procedure_checklist,
        # Phase P1: rich draft keys, all _draft suffix so they cannot be
        # mistaken for production payload keys.
        "rich_draft": rich,
        "pattern_levels_draft": rich.get("pattern_levels_draft"),
        "wave_derived_lines_draft": rich.get("wave_derived_lines_draft"),
        "structural_lines_draft": rich.get("structural_lines_draft"),
        "support_resistance_v2_draft": rich.get("support_resistance_v2_draft"),
        "trendline_context_draft": rich.get("trendline_context_draft"),
        "royal_road_procedure_checklist_draft": rich.get(
            "royal_road_procedure_checklist_draft"
        ),
        "warnings": draft.warnings,
    }

    return MonitorCase(
        chart_payload=chart_payload,
        ai_payload=ai_payload,
        source_payload=draft.model_dump(mode="json"),
        source="draft_from_market_snapshot",
    )


__all__ = ["build_monitor_case_from_draft_payload"]
