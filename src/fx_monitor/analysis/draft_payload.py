"""Build a :class:`RoyalRoadDraftPayload` from a :class:`MarketSnapshot`.

The draft is **observation only**:

- ``observation_only=True``
- ``used_in_final_action=False``
- ``entry_plan.entry_status="HOLD"``
- ``royal_road_procedure_checklist.p0_pass=False``

The rule engine refuses to return PASS for any payload with
``observation_only=True``, so this path can never produce READY.
"""

from __future__ import annotations

from typing import Any

from fx_monitor.analysis.pivots import detect_simple_pivots
from fx_monitor.analysis.rough_levels import build_rough_support_resistance
from fx_monitor.core.models import MarketSnapshot, PivotPoint, RoyalRoadDraftPayload


def _last_alternating_pivots(pivots: list[PivotPoint], n: int = 4) -> list[PivotPoint]:
    result: list[PivotPoint] = []
    for p in reversed(pivots):
        if not result or result[-1].kind != p.kind:
            result.append(p)
        if len(result) >= n:
            break
    return list(reversed(result))


def _rough_wave_context(pivots: list[PivotPoint]) -> dict[str, Any]:
    last4 = _last_alternating_pivots(pivots, 4)

    ctx: dict[str, Any] = {
        "schema_version": "rough_wave_context_v1",
        "observation_only": True,
        "used_in_final_action": False,
        "last_pivots": [
            {
                "index": p.index,
                "timestamp_utc": p.timestamp_utc.isoformat(),
                "price": p.price,
                "kind": p.kind,
            }
            for p in last4
        ],
        "rough_pattern_kind": "unknown",
        "warnings": [],
    }

    if len(last4) < 4:
        ctx["warnings"].append("insufficient_pivots_for_pattern")
        return ctx

    kinds = [p.kind for p in last4]
    prices = [p.price for p in last4]

    # HIGH LOW HIGH LOW: possible double top.
    if kinds == ["HIGH", "LOW", "HIGH", "LOW"]:
        rel = abs(prices[0] - prices[2]) / max(abs(prices[0]), 1e-9)
        if rel < 0.003:
            ctx["rough_pattern_kind"] = "possible_double_top"

    # LOW HIGH LOW HIGH: possible double bottom.
    if kinds == ["LOW", "HIGH", "LOW", "HIGH"]:
        rel = abs(prices[0] - prices[2]) / max(abs(prices[0]), 1e-9)
        if rel < 0.003:
            ctx["rough_pattern_kind"] = "possible_double_bottom"

    return ctx


def build_royal_road_draft_payload_from_snapshot(
    snapshot: MarketSnapshot,
) -> RoyalRoadDraftPayload:
    pivots = detect_simple_pivots(snapshot)
    sr = build_rough_support_resistance(pivots)
    wave = _rough_wave_context(pivots)

    warnings: list[str] = []
    warnings.extend(snapshot.warnings)
    warnings.extend(sr.get("warnings", []))
    warnings.extend(wave.get("warnings", []))

    entry_plan = {
        "schema_version": "entry_plan_draft_v1",
        "entry_status": "HOLD",
        "side": "NEUTRAL",
        "entry_price": None,
        "stop_price": None,
        "target_price": None,
        "rr": None,
        "reason_ja": "OHLC draft payload only. READY generation is disabled.",
    }

    selected_candidate = {
        "schema_version": "entry_candidate_draft_v1",
        "entry_type": "none",
        "status": "HOLD",
        "side": "NEUTRAL",
        "block_reasons": ["draft_payload_not_tradeable"],
    }

    checklist = {
        "schema_version": "royal_road_procedure_checklist_draft_v1",
        "p0_pass": False,
        "p0_missing_or_blocked": [
            "pattern_levels",
            "wave_derived_lines",
            "entry_plan_ready",
            "confirmation_candle",
            "rr",
        ],
        "summary_ja": "OHLCから作った下書きです。READY判定には使いません。",
        "steps": [
            {"key": "wave_pattern", "status": "UNKNOWN"},
            {"key": "wave_lines", "status": "UNKNOWN"},
            {"key": "breakout_confirmed", "status": "UNKNOWN"},
            {"key": "retest_confirmed", "status": "UNKNOWN"},
            {"key": "confirmation_candle", "status": "UNKNOWN"},
            {"key": "entry_price", "status": "UNKNOWN"},
            {"key": "stop_price", "status": "UNKNOWN"},
            {"key": "target_price", "status": "UNKNOWN"},
            {"key": "rr_ok", "status": "UNKNOWN"},
            {"key": "event_clear", "status": "UNKNOWN"},
        ],
    }

    return RoyalRoadDraftPayload(
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        source=snapshot.source,
        timestamp_utc=snapshot.candles[-1].timestamp_utc if snapshot.candles else None,
        pivots=pivots,
        rough_support_resistance=sr,
        rough_wave_context=wave,
        entry_plan=entry_plan,
        selected_entry_candidate=selected_candidate,
        royal_road_procedure_checklist=checklist,
        warnings=warnings,
    )


__all__ = ["build_royal_road_draft_payload_from_snapshot"]
