"""Phase P3 scaffold: compare a draft rich payload to a reference payload.

This is **offline analysis only**. It produces presence-style scores
between a ``rich_draft`` (synthesised from raw OHLC) and a ``reference``
royal-road payload (typically a captured production fixture).

The output never feeds READY, notification, or trading decisions. Tests
pin the safety flags. Future phases (P4+) may consume the metric for
gating their own promotions, but that is an explicit future step.

Comparison surface (deliberately small for the scaffold):

- pattern kind match
- WNL / WSL / WTP presence (and price gap when both sides have a price)
- SNL / SIL / STP / STL presence
- support/resistance zone count
- trendline count

Anything richer (precision/recall over multiple cases, cross-fixture
sweeps, ML metrics) is a future extension.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "rich_draft_compare_v1"

_WAVE_ROLES = ("entry_confirmation_line", "stop_candidate", "target_candidate")
_STRUCTURAL_KINDS = (
    "structural_neckline",
    "structural_invalidation",
    "structural_target",
    "structural_trendline",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _as_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _draft_pattern(draft: dict[str, Any]) -> dict[str, Any]:
    return draft.get("pattern_levels_draft") or {}


def _ref_pattern(reference: dict[str, Any]) -> dict[str, Any]:
    return reference.get("pattern_levels") or reference.get("pattern_levels_draft") or {}


def _draft_wave_lines(draft: dict[str, Any]) -> list[dict[str, Any]]:
    raw = draft.get("wave_derived_lines_draft") or []
    return raw if isinstance(raw, list) else []


def _ref_wave_lines(reference: dict[str, Any]) -> list[dict[str, Any]]:
    raw = reference.get("wave_derived_lines") or reference.get("wave_derived_lines_draft") or []
    return raw if isinstance(raw, list) else []


def _draft_structural_lines(draft: dict[str, Any]) -> list[dict[str, Any]]:
    block = draft.get("structural_lines_draft") or {}
    raw = block.get("lines") or []
    return raw if isinstance(raw, list) else []


def _ref_structural_lines(reference: dict[str, Any]) -> list[dict[str, Any]]:
    block = reference.get("structural_lines") or reference.get("structural_lines_draft") or {}
    raw = block.get("lines") or []
    return raw if isinstance(raw, list) else []


def _draft_sr_zones(draft: dict[str, Any]) -> list[dict[str, Any]]:
    block = draft.get("support_resistance_v2_draft") or {}
    raw = block.get("selected_level_zones_top5") or []
    return raw if isinstance(raw, list) else []


def _ref_sr_zones(reference: dict[str, Any]) -> list[dict[str, Any]]:
    block = (
        reference.get("support_resistance_v2")
        or reference.get("support_resistance_v2_draft")
        or {}
    )
    raw = block.get("selected_level_zones_top5") or []
    return raw if isinstance(raw, list) else []


def _draft_trendlines(draft: dict[str, Any]) -> list[dict[str, Any]]:
    block = draft.get("trendline_context_draft") or {}
    raw = block.get("selected_trendlines_top3") or []
    return raw if isinstance(raw, list) else []


def _ref_trendlines(reference: dict[str, Any]) -> list[dict[str, Any]]:
    block = reference.get("trendline_context") or reference.get("trendline_context_draft") or {}
    raw = block.get("selected_trendlines_top3") or []
    return raw if isinstance(raw, list) else []


def _wave_role_price_map(lines: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in lines:
        if not isinstance(line, dict):
            continue
        role = str(line.get("role") or "")
        price = _as_float(line.get("price"))
        if role and price is not None and role not in out:
            out[role] = price
    return out


def _structural_kind_set(lines: list[dict[str, Any]]) -> set[str]:
    return {
        str(line.get("kind"))
        for line in lines
        if isinstance(line, dict) and line.get("kind")
    }


def _anchor_match_count(
    draft_lines: list[dict[str, Any]],
    ref_lines: list[dict[str, Any]],
) -> int:
    """Count structural lines whose (kind, anchor_parts set) match."""

    def _key(line: dict[str, Any]) -> tuple[str, frozenset[str]]:
        return (
            str(line.get("kind") or ""),
            frozenset(str(a) for a in (line.get("anchor_parts") or [])),
        )

    ref_keys = {_key(line) for line in ref_lines if isinstance(line, dict)}
    matches = 0
    for line in draft_lines:
        if isinstance(line, dict) and _key(line) in ref_keys:
            matches += 1
    return matches


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compare_rich_draft_to_reference(
    *,
    draft: dict[str, Any],
    reference: dict[str, Any],
) -> dict[str, Any]:
    """Return a presence-style comparison record.

    All scores are in [0.0, 1.0].

    The output dict carries safety flags
    (``offline_analysis_only=True`` / ``used_for_ready=False`` /
    ``used_for_notification=False``) that tests pin in place.
    """
    if not isinstance(draft, dict) or not isinstance(reference, dict):
        raise TypeError("draft and reference must be dicts")

    draft_pat = _draft_pattern(draft)
    ref_pat = _ref_pattern(reference)
    draft_wave = _draft_wave_lines(draft)
    ref_wave = _ref_wave_lines(reference)
    draft_struct = _draft_structural_lines(draft)
    ref_struct = _ref_structural_lines(reference)
    draft_sr = _draft_sr_zones(draft)
    ref_sr = _ref_sr_zones(reference)
    draft_trend = _draft_trendlines(draft)
    ref_trend = _ref_trendlines(reference)

    # ------- pattern_match
    draft_kind = str(draft_pat.get("pattern_kind") or "unknown")
    ref_kind = str(ref_pat.get("pattern_kind") or "unknown")
    if draft_kind == "unknown" or ref_kind == "unknown":
        pattern_match = 0.0
    elif draft_kind == ref_kind:
        pattern_match = 1.0
    elif {draft_kind, ref_kind} == {"possible_double_top", "double_top"} or {
        draft_kind,
        ref_kind,
    } == {"possible_double_bottom", "double_bottom"}:
        # "possible_X" is the draft-side label; treat as same kind.
        pattern_match = 1.0
    else:
        pattern_match = 0.0

    mismatches: list[str] = []
    missing: list[str] = []
    warnings: list[str] = []

    if pattern_match < 1.0:
        mismatches.append(f"pattern_kind: draft={draft_kind} reference={ref_kind}")

    # ------- wave_line_presence (and price gap when both have price)
    draft_wave_prices = _wave_role_price_map(draft_wave)
    ref_wave_prices = _wave_role_price_map(ref_wave)

    wave_role_matches = 0
    wave_price_gaps: dict[str, float] = {}
    for role in _WAVE_ROLES:
        in_draft = role in draft_wave_prices
        in_ref = role in ref_wave_prices
        if in_draft and in_ref:
            wave_role_matches += 1
            ref_price = ref_wave_prices[role]
            if ref_price:
                wave_price_gaps[role] = abs(
                    draft_wave_prices[role] - ref_price
                ) / abs(ref_price)
        elif in_ref and not in_draft:
            missing.append(f"wave_line:{role}")
        elif in_draft and not in_ref:
            mismatches.append(f"wave_line:{role}_extra_in_draft")

    wave_line_presence = (
        wave_role_matches / len(_WAVE_ROLES) if _WAVE_ROLES else 0.0
    )

    # ------- structural_line_presence
    draft_kinds = _structural_kind_set(draft_struct)
    ref_kinds = _structural_kind_set(ref_struct)
    matched_struct_kinds = sum(1 for k in _STRUCTURAL_KINDS if k in draft_kinds and k in ref_kinds)
    for k in _STRUCTURAL_KINDS:
        if k in ref_kinds and k not in draft_kinds:
            missing.append(f"structural_line:{k}")
    structural_line_presence = (
        matched_struct_kinds / len(_STRUCTURAL_KINDS) if _STRUCTURAL_KINDS else 0.0
    )
    structural_anchor_matches = _anchor_match_count(draft_struct, ref_struct)

    # ------- sr_presence (zone-count overlap, capped at 1.0)
    sr_presence = (
        min(len(draft_sr), len(ref_sr)) / max(len(ref_sr), 1) if ref_sr else 0.0
    )
    if ref_sr and not draft_sr:
        missing.append("support_resistance:zones")

    # ------- trendline_presence
    trendline_presence = (
        min(len(draft_trend), len(ref_trend)) / max(len(ref_trend), 1)
        if ref_trend
        else 0.0
    )
    if ref_trend and not draft_trend:
        missing.append("trendline_context:lines")

    if not draft_pat:
        warnings.append("draft_pattern_levels_missing")
    if not ref_pat:
        warnings.append("reference_pattern_levels_missing")

    return {
        "schema_version": SCHEMA_VERSION,
        "offline_analysis_only": True,
        "used_for_ready": False,
        "used_for_notification": False,
        "scores": {
            "pattern_match": pattern_match,
            "wave_line_presence": wave_line_presence,
            "structural_line_presence": structural_line_presence,
            "sr_presence": sr_presence,
            "trendline_presence": trendline_presence,
        },
        "counts": {
            "draft_wave_lines": len(draft_wave),
            "ref_wave_lines": len(ref_wave),
            "draft_structural_lines": len(draft_struct),
            "ref_structural_lines": len(ref_struct),
            "structural_anchor_matches": structural_anchor_matches,
            "draft_sr_zones": len(draft_sr),
            "ref_sr_zones": len(ref_sr),
            "draft_trendlines": len(draft_trend),
            "ref_trendlines": len(ref_trend),
        },
        "wave_price_gaps": wave_price_gaps,
        "missing": missing,
        "mismatches": mismatches,
        "warnings": warnings,
    }


__all__ = ["compare_rich_draft_to_reference", "SCHEMA_VERSION"]
