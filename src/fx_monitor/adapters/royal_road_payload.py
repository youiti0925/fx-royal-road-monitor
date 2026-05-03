"""Adapter: existing royal-road decision/preview payload -> MonitorCase.

This is intentionally defensive. Goals:
- Preserve all rich evidence under MonitorCase.ai_payload for AI review.
- Derive a minimal, deterministic ChartPayload for the legacy rule path.
- Never raise on missing optional fields; return safe defaults.
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
    TriggerInfo,
)


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    if isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return datetime.now(timezone.utc)


def _upper(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).upper()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_symbol(raw: dict[str, Any]) -> str:
    return str(
        raw.get("symbol")
        or raw.get("ticker")
        or raw.get("instrument")
        or (raw.get("meta") or {}).get("symbol")
        or "UNKNOWN"
    )


def _extract_timeframe(raw: dict[str, Any]) -> str:
    return str(
        raw.get("timeframe")
        or raw.get("tf")
        or (raw.get("meta") or {}).get("timeframe")
        or "UNKNOWN"
    )


def _extract_timestamp(raw: dict[str, Any]) -> datetime:
    return _parse_ts(
        raw.get("timestamp_utc")
        or raw.get("timestamp")
        or raw.get("current_ts")
        or (raw.get("meta") or {}).get("timestamp_utc")
    )


def _extract_entry_plan(raw: dict[str, Any]) -> dict[str, Any]:
    ep = raw.get("entry_plan") or {}
    return ep if isinstance(ep, dict) else {}


def _extract_selected_candidate(raw: dict[str, Any]) -> dict[str, Any]:
    c = raw.get("selected_entry_candidate") or {}
    return c if isinstance(c, dict) else {}


def _extract_checklist(raw: dict[str, Any]) -> dict[str, Any]:
    c = raw.get("royal_road_procedure_checklist") or {}
    return c if isinstance(c, dict) else {}


def _extract_fundamental(raw: dict[str, Any]) -> dict[str, Any]:
    fs = raw.get("fundamental_sidebar") or {}
    return fs if isinstance(fs, dict) else {}


def _side_to_bias(side: Any) -> str:
    s = _upper(side, "NEUTRAL")
    if s == "BUY":
        return "long"
    if s == "SELL":
        return "short"
    return "none"


def _status_to_trigger(entry_status: str) -> TriggerInfo:
    status = _upper(entry_status, "HOLD")

    if status in ("READY", "WAIT_EVENT_CLEAR"):
        return TriggerInfo(type="retest", occurred=True)

    if status == "WAIT_RETEST":
        return TriggerInfo(type="breakout", occurred=True)

    if status in ("WAIT_BREAKOUT", "HOLD", "WAIT_TRIGGER"):
        return TriggerInfo(type="none", occurred=False)

    return TriggerInfo(type="none", occurred=False)


def _event_blocked(raw: dict[str, Any]) -> bool:
    fs = _extract_fundamental(raw)
    if _upper(fs.get("event_risk_status")) == "BLOCK":
        return True

    checklist = _extract_checklist(raw)
    for step in checklist.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        key = step.get("key")
        if key in ("event_clear", "event") and _upper(step.get("status")) == "BLOCK":
            return True

    return False


def _derive_htf_context(raw: dict[str, Any], side: str) -> HtfContext:
    """Conservative HTF context for legacy ChartPayload compatibility.

    The rich AI payload remains the source of truth. This only exists so
    old rule_engine paths can still run.
    """
    dow = raw.get("dow_structure_review") or {}
    trend = _upper(dow.get("trend"), "")

    if trend == "UP":
        h4: str = "up"
    elif trend == "DOWN":
        h4 = "down"
    elif trend in ("RANGE", "MIXED"):
        h4 = "range"
    else:
        bias = _side_to_bias(side)
        h4 = "up" if bias == "long" else ("down" if bias == "short" else "range")

    d1 = h4 if h4 in ("up", "down") else "range"

    levels: list[float] = []
    sr = raw.get("support_resistance_v2") or {}
    for z in sr.get("selected_level_zones_top5", []) or []:
        if not isinstance(z, dict):
            continue
        for key in ("price", "mid", "price_low", "price_high"):
            if key in z:
                levels.append(_as_float(z[key]))
                break

    return HtfContext(h4_trend=h4, d1_trend=d1, key_levels=levels)


def _derive_ltf_context(raw: dict[str, Any], side: str) -> LtfContext:
    pattern = raw.get("pattern_levels") or {}
    parts = pattern.get("parts") or {}

    prices: list[float] = []
    if isinstance(parts, dict):
        for p in parts.values():
            if isinstance(p, dict):
                price = _as_float(p.get("price"), default=0.0)
                if price:
                    prices.append(price)

    ep = _extract_entry_plan(raw)
    prices.extend(
        [
            _as_float(ep.get("entry_price"), 0.0),
            _as_float(ep.get("stop_price"), 0.0),
            _as_float(ep.get("target_price") or ep.get("target_extended_price"), 0.0),
        ]
    )
    prices = [p for p in prices if p > 0]

    last_swing_high = max(prices) if prices else 1.0
    last_swing_low = min(prices) if prices else 0.9
    if last_swing_high <= last_swing_low:
        last_swing_high = last_swing_low + 0.0001

    bias = _side_to_bias(side)
    if bias == "long":
        structure = "HH-HL"
    elif bias == "short":
        structure = "LH-LL"
    else:
        structure = "range"

    atr = abs(last_swing_high - last_swing_low) / 10.0
    if atr <= 0:
        atr = 0.0001

    return LtfContext(
        structure=structure,
        last_swing_high=last_swing_high,
        last_swing_low=last_swing_low,
        atr_14=atr,
    )


_AI_PAYLOAD_KEYS = (
    "symbol",
    "timeframe",
    "timestamp_utc",
    "entry_plan",
    "selected_entry_candidate",
    "royal_road_procedure_checklist",
    "structural_lines",
    "pattern_levels",
    "wave_derived_lines",
    "trendline_context",
    "support_resistance_v2",
    "fundamental_sidebar",
    "dow_structure_review",
    "breakout_quality_gate",
    "candlestick_anatomy_review",
)


def _build_ai_payload(raw: dict[str, Any], chart_image_path: str | None) -> dict[str, Any]:
    """Pick the rich royal-road fields we want to send to AI reviewers."""
    payload: dict[str, Any] = {k: raw.get(k) for k in _AI_PAYLOAD_KEYS if k in raw}
    payload["chart_image_path"] = chart_image_path
    payload["source"] = "existing_royal_road_payload"
    return payload


def build_monitor_case_from_royal_road_payload(
    raw: dict[str, Any],
    *,
    chart_image_path: str | None = None,
) -> MonitorCase:
    """Convert an existing royal-road decision/preview payload into MonitorCase."""
    if not isinstance(raw, dict):
        raise TypeError("raw payload must be dict")

    symbol = _extract_symbol(raw)
    timeframe = _extract_timeframe(raw)
    ts = _extract_timestamp(raw)

    ep = _extract_entry_plan(raw)
    selected = _extract_selected_candidate(raw)

    entry_status = str(selected.get("status") or ep.get("entry_status") or "HOLD")
    side = str(selected.get("side") or ep.get("side") or raw.get("side") or "NEUTRAL")

    chart_payload = ChartPayload(
        symbol=symbol,
        timeframe=timeframe,
        timestamp_utc=ts,
        htf=_derive_htf_context(raw, side),
        ltf=_derive_ltf_context(raw, side),
        trigger=_status_to_trigger(entry_status),
        calendar=CalendarInfo(high_impact_within_15min=_event_blocked(raw)),
    )

    ai_payload = _build_ai_payload(
        {
            **raw,
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp_utc": ts.isoformat(),
        },
        chart_image_path,
    )

    return MonitorCase(
        chart_payload=chart_payload,
        ai_payload=ai_payload,
        source_payload=raw,
        source="existing_royal_road_payload",
        chart_image_path=chart_image_path,
    )


__all__ = ["build_monitor_case_from_royal_road_payload"]
