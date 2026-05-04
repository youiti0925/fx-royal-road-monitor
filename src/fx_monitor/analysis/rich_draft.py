"""Phase P1: build royal-road-style "rich draft" keys from raw OHLC pivots.

Every produced object carries:

- ``source = "draft"``
- ``observation_only = True``
- ``used_in_final_action = False``

and the top-level bag has ``ready_eligible = False``. All key names use a
``_draft`` suffix so they cannot be mistaken for production payload keys
(``pattern_levels`` / ``wave_derived_lines`` / ``structural_lines`` / ...).

This module never touches the rule engine, the notifier, or any AI
prompt / schema. It only synthesises observation-only fields for the
existing draft pipeline.
"""

from __future__ import annotations

from typing import Any

from fx_monitor.core.models import PivotPoint


def _pivot_dict(p: PivotPoint) -> dict[str, Any]:
    return {
        "index": p.index,
        "timestamp_utc": p.timestamp_utc.isoformat(),
        "price": p.price,
        "kind": p.kind,
        "strength": p.strength,
    }


def _last_alternating_pivots(pivots: list[PivotPoint], n: int = 4) -> list[PivotPoint]:
    result: list[PivotPoint] = []
    for p in reversed(pivots):
        if not result or result[-1].kind != p.kind:
            result.append(p)
        if len(result) >= n:
            break
    return list(reversed(result))


def _rough_pattern_from_last4(last4: list[PivotPoint]) -> tuple[str, str]:
    if len(last4) < 4:
        return "unknown", "NEUTRAL"

    kinds = [p.kind for p in last4]
    prices = [p.price for p in last4]

    if kinds == ["HIGH", "LOW", "HIGH", "LOW"]:
        rel = abs(prices[0] - prices[2]) / max(abs(prices[0]), 1e-9)
        if rel < 0.003:
            return "possible_double_top", "SELL"

    if kinds == ["LOW", "HIGH", "LOW", "HIGH"]:
        rel = abs(prices[0] - prices[2]) / max(abs(prices[0]), 1e-9)
        if rel < 0.003:
            return "possible_double_bottom", "BUY"

    return "unknown", "NEUTRAL"


def build_pattern_levels_draft(pivots: list[PivotPoint]) -> dict[str, Any]:
    last4 = _last_alternating_pivots(pivots, 4)
    pattern_kind, side = _rough_pattern_from_last4(last4)

    parts: dict[str, Any] = {}
    warnings: list[str] = []

    if len(last4) < 4:
        warnings.append("insufficient_pivots_for_pattern_levels_draft")
    elif pattern_kind == "possible_double_top":
        labels = ["P1", "NL", "P2", "BR"]
        parts = {label: _pivot_dict(p) for label, p in zip(labels, last4)}
    elif pattern_kind == "possible_double_bottom":
        labels = ["B1", "NL", "B2", "BR"]
        parts = {label: _pivot_dict(p) for label, p in zip(labels, last4)}
    else:
        warnings.append("no_supported_pattern_levels_draft")

    nl_price = None
    nl = parts.get("NL")
    if isinstance(nl, dict):
        nl_price = nl.get("price")

    return {
        "schema_version": "pattern_levels_draft_v1",
        "source": "draft",
        "observation_only": True,
        "used_in_final_action": False,
        "available": bool(parts),
        "pattern_kind": pattern_kind,
        "side": side,
        "parts": parts,
        "trigger_line_price": nl_price,
        "warnings": warnings,
        "confidence": 0.35 if parts else 0.0,
    }


def build_wave_derived_lines_draft(
    pattern_levels_draft: dict[str, Any],
) -> list[dict[str, Any]]:
    if not pattern_levels_draft.get("available"):
        return []

    parts = pattern_levels_draft.get("parts") or {}
    side = pattern_levels_draft.get("side") or "NEUTRAL"
    pattern_kind = pattern_levels_draft.get("pattern_kind") or "unknown"

    nl = parts.get("NL") or {}
    br = parts.get("BR") or {}

    lines: list[dict[str, Any]] = []

    if nl.get("price") is not None:
        lines.append(
            {
                "id": "WNL_D1",
                "schema_version": "wave_derived_line_draft_v1",
                "source": "draft",
                "observation_only": True,
                "used_in_final_action": False,
                "role": "entry_confirmation_line",
                "label": "WNL",
                "price": nl["price"],
                "anchor_parts": ["NL"],
                "side": side,
                "confidence": 0.35,
                "warnings": ["draft_line_not_production_evidence"],
            }
        )

    invalid_anchor = "P2" if pattern_kind == "possible_double_top" else "B2"
    invalid = parts.get(invalid_anchor) or {}
    if invalid.get("price") is not None:
        lines.append(
            {
                "id": "WSL_D1",
                "schema_version": "wave_derived_line_draft_v1",
                "source": "draft",
                "observation_only": True,
                "used_in_final_action": False,
                "role": "stop_candidate",
                "label": "WSL",
                "price": invalid["price"],
                "anchor_parts": [invalid_anchor],
                "side": side,
                "confidence": 0.30,
                "warnings": ["draft_stop_line_not_tradeable"],
            }
        )

    if br.get("price") is not None:
        lines.append(
            {
                "id": "WTP_D1",
                "schema_version": "wave_derived_line_draft_v1",
                "source": "draft",
                "observation_only": True,
                "used_in_final_action": False,
                "role": "target_candidate",
                "label": "WTP",
                "price": br["price"],
                "anchor_parts": ["BR"],
                "side": side,
                "confidence": 0.25,
                "warnings": ["draft_target_line_not_tradeable"],
            }
        )

    return lines


def build_structural_lines_draft(
    pattern_levels_draft: dict[str, Any],
) -> dict[str, Any]:
    parts = pattern_levels_draft.get("parts") or {}
    pattern_kind = pattern_levels_draft.get("pattern_kind") or "unknown"
    warnings: list[str] = []
    lines: list[dict[str, Any]] = []

    if (parts.get("NL") or {}).get("price") is not None:
        lines.append(
            {
                "id": "SNL_D1",
                "kind": "structural_neckline",
                "role": "entry_trigger",
                "source": "draft",
                "observation_only": True,
                "used_in_final_action": False,
                "price": parts["NL"]["price"],
                "anchor_parts": ["NL"],
                "confidence": 0.35,
                "warnings": ["draft_structural_line"],
            }
        )

    invalid_anchor = "P2" if pattern_kind == "possible_double_top" else "B2"
    if (parts.get(invalid_anchor) or {}).get("price") is not None:
        lines.append(
            {
                "id": "SIL_D1",
                "kind": "structural_invalidation",
                "role": "stop_candidate",
                "source": "draft",
                "observation_only": True,
                "used_in_final_action": False,
                "price": parts[invalid_anchor]["price"],
                "anchor_parts": [invalid_anchor],
                "confidence": 0.30,
                "warnings": ["draft_structural_line"],
            }
        )

    if (parts.get("BR") or {}).get("price") is not None:
        lines.append(
            {
                "id": "STP_D1",
                "kind": "structural_target",
                "role": "target_candidate",
                "source": "draft",
                "observation_only": True,
                "used_in_final_action": False,
                "price": parts["BR"]["price"],
                "anchor_parts": ["BR"],
                "confidence": 0.25,
                "warnings": ["draft_structural_line"],
            }
        )

    if pattern_kind == "possible_double_top":
        a, b = "P1", "P2"
        role = "top_structure_line"
    elif pattern_kind == "possible_double_bottom":
        a, b = "B1", "B2"
        role = "bottom_structure_line"
    else:
        a, b, role = "", "", ""

    if a and b and isinstance(parts.get(a), dict) and isinstance(parts.get(b), dict):
        p1 = parts[a]
        p2 = parts[b]
        try:
            dx = float(p2["index"]) - float(p1["index"])
            slope = (float(p2["price"]) - float(p1["price"])) / dx if dx else 0.0
        except Exception:
            slope = 0.0

        lines.append(
            {
                "id": "STL_D1",
                "kind": "structural_trendline",
                "role": role,
                "source": "draft",
                "observation_only": True,
                "used_in_final_action": False,
                "anchor_parts": [a, b],
                "slope": slope,
                "confidence": 0.30,
                "warnings": ["draft_trendline_not_numeric_validated"],
            }
        )
    else:
        warnings.append("structural_trendline_draft_not_available")

    counts = {
        "total": len(lines),
        "structural_neckline": sum(1 for x in lines if x.get("kind") == "structural_neckline"),
        "structural_invalidation": sum(
            1 for x in lines if x.get("kind") == "structural_invalidation"
        ),
        "structural_target": sum(1 for x in lines if x.get("kind") == "structural_target"),
        "structural_trendline": sum(1 for x in lines if x.get("kind") == "structural_trendline"),
    }

    return {
        "schema_version": "structural_lines_draft_v1",
        "source": "draft",
        "observation_only": True,
        "used_in_final_action": False,
        "lines": lines,
        "counts": counts,
        "warnings": warnings,
    }


def build_trendline_context_draft(
    pattern_levels_draft: dict[str, Any],
) -> dict[str, Any]:
    structural = build_structural_lines_draft(pattern_levels_draft)
    trendlines = [
        line
        for line in structural.get("lines", [])
        if line.get("kind") == "structural_trendline"
    ]

    return {
        "schema_version": "trendline_context_draft_v1",
        "source": "draft",
        "observation_only": True,
        "used_in_final_action": False,
        "selected_trendlines_top3": trendlines[:3],
        "warnings": (
            ["draft_trendlines_not_numeric_production_evidence"]
            if trendlines
            else ["no_draft_trendline"]
        ),
    }


def build_royal_road_procedure_checklist_draft(
    *,
    pattern_levels_draft: dict[str, Any],
    wave_derived_lines_draft: list[dict[str, Any]],
    structural_lines_draft: dict[str, Any],
    support_resistance_v2_draft: dict[str, Any],
    trendline_context_draft: dict[str, Any],
) -> dict[str, Any]:
    pattern_available = bool(pattern_levels_draft.get("available"))
    wave_lines_available = len(wave_derived_lines_draft) >= 3
    structural_available = (structural_lines_draft.get("counts") or {}).get("total", 0) > 0
    sr_available = bool((support_resistance_v2_draft.get("selected_level_zones_top5") or []))
    trend_available = bool((trendline_context_draft.get("selected_trendlines_top3") or []))

    steps = [
        {"key": "environment", "status": "UNKNOWN", "importance": "P0"},
        {"key": "dow_structure", "status": "UNKNOWN", "importance": "P0"},
        {"key": "support_resistance", "status": "WAIT" if sr_available else "UNKNOWN", "importance": "P1"},
        {"key": "trendline_context", "status": "WAIT" if trend_available else "UNKNOWN", "importance": "P1"},
        {"key": "structural_lines", "status": "WAIT" if structural_available else "UNKNOWN", "importance": "P1"},
        {"key": "wave_pattern", "status": "WAIT" if pattern_available else "UNKNOWN", "importance": "P0"},
        {"key": "wave_lines", "status": "WAIT" if wave_lines_available else "UNKNOWN", "importance": "P0"},
        {"key": "breakout_confirmed", "status": "UNKNOWN", "importance": "P0"},
        {"key": "retest_confirmed", "status": "UNKNOWN", "importance": "P0"},
        {"key": "confirmation_candle", "status": "UNKNOWN", "importance": "P0"},
        {"key": "entry_price", "status": "UNKNOWN", "importance": "P0"},
        {"key": "stop_price", "status": "UNKNOWN", "importance": "P0"},
        {"key": "target_price", "status": "UNKNOWN", "importance": "P0"},
        {"key": "rr_ok", "status": "UNKNOWN", "importance": "P0"},
        {"key": "event_clear", "status": "UNKNOWN", "importance": "P0"},
    ]

    return {
        "schema_version": "royal_road_procedure_checklist_draft_v1",
        "source": "draft",
        "observation_only": True,
        "used_in_final_action": False,
        "p0_pass": False,
        "p0_missing_or_blocked": [
            "environment",
            "dow_structure",
            "breakout_confirmed",
            "retest_confirmed",
            "confirmation_candle",
            "entry_price",
            "stop_price",
            "target_price",
            "rr_ok",
            "event_clear",
        ],
        "summary_ja": (
            "Rich draft keys are present, but this remains observation-only "
            "and cannot be READY."
        ),
        "steps": steps,
        "warnings": ["rich_draft_not_ready_eligible"],
    }


def build_rich_draft(
    *,
    pivots: list[PivotPoint],
    rough_support_resistance: dict[str, Any],
) -> dict[str, Any]:
    pattern = build_pattern_levels_draft(pivots)
    wave_lines = build_wave_derived_lines_draft(pattern)
    structural = build_structural_lines_draft(pattern)
    trendline = build_trendline_context_draft(pattern)

    sr_zones = rough_support_resistance.get("selected_level_zones_top5") or []
    sr_warnings = list(rough_support_resistance.get("warnings") or [])
    sr_warnings.append("draft_support_resistance_not_production_evidence")

    support_resistance_v2_draft = {
        "schema_version": "support_resistance_v2_draft_v1",
        "source": "draft",
        "observation_only": True,
        "used_in_final_action": False,
        "selected_level_zones_top5": sr_zones,
        "warnings": sr_warnings,
    }

    checklist = build_royal_road_procedure_checklist_draft(
        pattern_levels_draft=pattern,
        wave_derived_lines_draft=wave_lines,
        structural_lines_draft=structural,
        support_resistance_v2_draft=support_resistance_v2_draft,
        trendline_context_draft=trendline,
    )

    return {
        "schema_version": "rich_royal_road_draft_v1",
        "source": "draft",
        "observation_only": True,
        "used_in_final_action": False,
        "pattern_levels_draft": pattern,
        "wave_derived_lines_draft": wave_lines,
        "structural_lines_draft": structural,
        "support_resistance_v2_draft": support_resistance_v2_draft,
        "trendline_context_draft": trendline,
        "royal_road_procedure_checklist_draft": checklist,
        "ready_eligible": False,
        "warnings": ["rich_draft_not_production_evidence", "ready_forbidden"],
    }


__all__ = [
    "build_rich_draft",
    "build_pattern_levels_draft",
    "build_wave_derived_lines_draft",
    "build_structural_lines_draft",
    "build_trendline_context_draft",
    "build_royal_road_procedure_checklist_draft",
]
