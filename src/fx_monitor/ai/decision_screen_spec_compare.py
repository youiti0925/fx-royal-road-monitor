"""Compare two AI-authored decision screen specs.

Output is **observation only** — never feeds READY / notification /
trading / order execution. The comparator never silently picks one
side; mismatches become ``conflicts`` so the renderer can paint them
explicitly.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "decision_screen_spec_compare_v1"


def _spec_dict(spec: Any) -> dict[str, Any]:
    if isinstance(spec, dict):
        return spec
    if hasattr(spec, "model_dump"):
        return spec.model_dump(mode="json")
    return {}


def _lines(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return list(spec.get("lines") or [])


def _zones(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return list(spec.get("zones") or [])


def _step_status_map(spec: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for s in spec.get("procedure_steps") or []:
        if isinstance(s, dict) and s.get("key"):
            out[str(s["key"])] = str(s.get("status") or "UNKNOWN")
    return out


def _line_key(line: dict[str, Any]) -> tuple[str, str, frozenset[str]]:
    return (
        str(line.get("kind") or ""),
        str(line.get("role") or ""),
        frozenset(str(a) for a in (line.get("anchor_points") or [])),
    )


def _close_price(a: float | None, b: float | None, tol: float = 0.005) -> bool:
    if a is None or b is None:
        return False
    if a == 0 and b == 0:
        return True
    base = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / base <= tol


def compare_decision_screen_specs(
    *,
    openai_spec: Any,
    claude_spec: Any,
) -> dict[str, Any]:
    o = _spec_dict(openai_spec)
    c = _spec_dict(claude_spec)

    o_unknown = (o.get("final_status") or "UNKNOWN") == "UNKNOWN" or not o.get("symbol")
    c_unknown = (c.get("final_status") or "UNKNOWN") == "UNKNOWN" or not c.get("symbol")

    matched_lines: list[dict[str, Any]] = []
    openai_only: list[dict[str, Any]] = []
    claude_only: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    o_lines = _lines(o)
    c_lines = _lines(c)
    matched_o_idx: set[int] = set()
    matched_c_idx: set[int] = set()

    for i, ol in enumerate(o_lines):
        ok = _line_key(ol)
        for j, cl in enumerate(c_lines):
            if j in matched_c_idx:
                continue
            ck = _line_key(cl)
            if ok != ck:
                continue
            if _close_price(ol.get("price"), cl.get("price")):
                matched_lines.append(
                    {
                        "kind": ol.get("kind"),
                        "role": ol.get("role"),
                        "anchor_points": list(ol.get("anchor_points") or []),
                        "openai_id": ol.get("id"),
                        "claude_id": cl.get("id"),
                        "openai_price": ol.get("price"),
                        "claude_price": cl.get("price"),
                    }
                )
                matched_o_idx.add(i)
                matched_c_idx.add(j)
                break
            else:
                conflicts.append(
                    {
                        "kind": ol.get("kind"),
                        "role": ol.get("role"),
                        "openai_id": ol.get("id"),
                        "claude_id": cl.get("id"),
                        "openai_price": ol.get("price"),
                        "claude_price": cl.get("price"),
                        "reason": "same kind/role/anchor but price differs",
                    }
                )
                matched_o_idx.add(i)
                matched_c_idx.add(j)
                break

    for i, ol in enumerate(o_lines):
        if i not in matched_o_idx:
            openai_only.append(ol)
    for j, cl in enumerate(c_lines):
        if j not in matched_c_idx:
            claude_only.append(cl)

    # Procedure step diffs.
    o_steps = _step_status_map(o)
    c_steps = _step_status_map(c)
    step_disagreements: list[dict[str, Any]] = []
    for key in sorted(set(o_steps) | set(c_steps)):
        os_status = o_steps.get(key, "MISSING")
        cs_status = c_steps.get(key, "MISSING")
        if os_status != cs_status:
            step_disagreements.append(
                {"step": key, "openai": os_status, "claude": cs_status}
            )

    side_match = (o.get("side") or "NEUTRAL") == (c.get("side") or "NEUTRAL")
    final_match = (o.get("final_status") or "UNKNOWN") == (
        c.get("final_status") or "UNKNOWN"
    )

    if o_unknown or c_unknown:
        agreement = "UNKNOWN"
    elif (
        not openai_only
        and not claude_only
        and not conflicts
        and side_match
        and final_match
        and not step_disagreements
    ):
        agreement = "AGREE"
    elif matched_lines and (
        len(openai_only) + len(claude_only) + len(conflicts) <= 2
    ) and side_match:
        agreement = "PARTIAL"
    else:
        agreement = "DISAGREE"

    summary_ja_parts: list[str] = []
    if agreement == "AGREE":
        summary_ja_parts.append("OpenAIとClaudeはほぼ一致しています。")
    elif agreement == "PARTIAL":
        summary_ja_parts.append("OpenAIとClaudeは一部一致しています。")
    elif agreement == "DISAGREE":
        summary_ja_parts.append("OpenAIとClaudeで判断が分かれています。")
    else:
        summary_ja_parts.append("AIによる王道判定画面が未完成です。")
    if conflicts:
        summary_ja_parts.append(f"価格不一致の線: {len(conflicts)}件。")
    if step_disagreements:
        summary_ja_parts.append(f"王道手順の評価不一致: {len(step_disagreements)}項目。")

    return {
        "schema_version": SCHEMA_VERSION,
        "observation_only": True,
        "used_for_ready": False,
        "used_for_notification": False,
        "used_for_trading": False,
        "agreement": agreement,
        "side_match": side_match,
        "final_status_match": final_match,
        "matched_lines": matched_lines,
        "openai_only": openai_only,
        "claude_only": claude_only,
        "conflicts": conflicts,
        "step_disagreements": step_disagreements,
        "summary_ja": " / ".join(summary_ja_parts),
    }


__all__ = ["compare_decision_screen_specs", "SCHEMA_VERSION"]
