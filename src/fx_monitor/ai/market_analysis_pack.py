"""Build the market analysis pack the AI receives as input.

This pack is **material**, not the answer. It must not pre-decide the
royal-road verdict, must not pick the "right" lines, and must not draw
the screen. The AI uses it (plus the knowledge pack) to author its own
decision_screen_spec.
"""

from __future__ import annotations

from typing import Any

from ..core.models import MarketSnapshot, RoyalRoadDraftPayload


def _candle_dict(c: Any) -> dict[str, Any]:
    return {
        "timestamp_utc": getattr(c, "timestamp_utc", None).isoformat()
        if getattr(c, "timestamp_utc", None)
        else None,
        "open": c.open,
        "high": c.high,
        "low": c.low,
        "close": c.close,
        "volume": c.volume,
    }


def build_market_analysis_pack(
    *,
    snapshot: MarketSnapshot | dict[str, Any],
    rich_draft: dict[str, Any] | RoyalRoadDraftPayload,
    diagnostics: dict[str, Any],
    knowledge_pack_text: str,
    knowledge_excerpt_chars: int = 6000,
) -> dict[str, Any]:
    """Pack everything the AI needs into a single dict.

    The pack is observation-only; the safety flags inside diagnostics
    are passed through verbatim so the AI sees the same hard contract
    we enforce on its output.
    """
    # MarketSnapshot -> plain dict (or accept dict directly).
    if isinstance(snapshot, MarketSnapshot):
        snap = {
            "symbol": snapshot.symbol,
            "timeframe": snapshot.timeframe,
            "source": snapshot.source,
            "candles": [_candle_dict(c) for c in snapshot.candles],
            "warnings": list(snapshot.warnings),
        }
    else:
        snap = dict(snapshot or {})

    if isinstance(rich_draft, RoyalRoadDraftPayload):
        rich = rich_draft.rich_draft or {}
        pivots = [p.model_dump(mode="json") for p in rich_draft.pivots]
    else:
        rich = (rich_draft or {})
        pivots = []

    knowledge_excerpt = (
        (knowledge_pack_text or "")[:knowledge_excerpt_chars]
        if knowledge_pack_text
        else ""
    )

    return {
        "schema_version": "market_analysis_pack_v1",
        "observation_only": True,
        "used_for_ready": False,
        "used_for_notification": False,
        "used_for_trading": False,
        "symbol": snap.get("symbol", "UNKNOWN"),
        "timeframe": snap.get("timeframe", "UNKNOWN"),
        "snapshot": snap,
        "pivots": pivots,
        "rich_draft": {
            "pattern_levels_draft": rich.get("pattern_levels_draft"),
            "wave_derived_lines_draft": rich.get("wave_derived_lines_draft"),
            "structural_lines_draft": rich.get("structural_lines_draft"),
            "support_resistance_v2_draft": rich.get("support_resistance_v2_draft"),
            "trendline_context_draft": rich.get("trendline_context_draft"),
            "royal_road_procedure_checklist_draft": rich.get(
                "royal_road_procedure_checklist_draft"
            ),
            "ready_eligible": False,
        },
        "diagnostics_safety": {
            "decision_level": ((diagnostics or {}).get("decision") or {}).get("level"),
            "ready_allowed": ((diagnostics or {}).get("safety") or {}).get(
                "ready_allowed"
            ),
            "dispatch_called": ((diagnostics or {}).get("safety") or {}).get(
                "dispatch_called"
            ),
        },
        "knowledge_pack_excerpt": knowledge_excerpt,
        "instructions_for_ai": [
            "あなたは王道手順の分析者です。売買判定ではありません。",
            "システムが描いた下書き線を盲信せず、必要なら採用しない判断をしてください。",
            "根拠が弱い線は採用しないでください。採用した線には reason_ja を必ず書く。",
            "READY通知を許可しないでください。",
            "売買可能に見せないでください。",
            "不明ならUNKNOWNにしてください。",
        ],
    }


__all__ = ["build_market_analysis_pack"]
