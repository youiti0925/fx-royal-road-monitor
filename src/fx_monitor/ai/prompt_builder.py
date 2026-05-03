"""Build the AI review prompt.

Per AI_REVIEW_POLICY.md, every call must include the *full* knowledge pack,
the JSON schema, and the structured payload. We do not trim. Optimization
(prompt caching) is the API's job, not ours.

The builder accepts either a legacy ChartPayload, a rich MonitorCase, or a
plain dict. MonitorCase is preferred because it carries the full royal-road
evidence (entry_plan, structural_lines, checklist, ...).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..core.models import ChartPayload, MonitorCase
from ..knowledge.loader import KnowledgePack, load_knowledge_pack
from .schema import schema_as_json

SYSTEM_INSTRUCTION = (
    "You are a royal-road procedure auditor for FX charts. You are NOT a "
    "signal generator. Use ONLY the royal-road knowledge pack and the "
    "structured payload (and image, if provided) below. Do not rely on "
    "general market knowledge or recent events. Do not hallucinate values "
    "that are not in the payload. If information is missing, return verdict "
    "UNKNOWN. Do not output verdict PASS unless every P0 step listed in the "
    "knowledge pack is PASS (wave_pattern, neckline, breakout, retest, "
    "confirmation_candle, entry, stop, target, rr, event). Respond with a "
    "single JSON object that strictly matches the provided JSON schema, with "
    "a `steps` array covering every required step key. Do not add any prose "
    "before or after the JSON."
)


@dataclass(frozen=True)
class BuiltPrompt:
    system: str
    user: str

    def total_chars(self) -> int:
        return len(self.system) + len(self.user)


def _payload_to_jsonable(
    payload: ChartPayload | MonitorCase | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(payload, MonitorCase):
        return {
            "chart_payload": payload.chart_payload.model_dump(mode="json"),
            "ai_payload": payload.ai_payload,
            "chart_image_path": payload.chart_image_path,
            "source": payload.source,
        }
    if isinstance(payload, ChartPayload):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return payload
    raise TypeError(f"Unsupported payload type: {type(payload).__name__}")


def build_prompt(
    payload: ChartPayload | MonitorCase | dict[str, Any],
    pack: KnowledgePack | None = None,
) -> BuiltPrompt:
    if pack is None:
        pack = load_knowledge_pack()

    payload_json = json.dumps(
        _payload_to_jsonable(payload),
        indent=2,
        ensure_ascii=False,
        default=str,
    )
    user = (
        "## Royal Road Knowledge Pack (verbatim)\n"
        f"{pack.text}\n\n"
        "## Required output JSON schema\n"
        "```json\n"
        f"{schema_as_json()}\n"
        "```\n\n"
        "## Current chart payload\n"
        "```json\n"
        f"{payload_json}\n"
        "```\n\n"
        "## Task\n"
        "Apply the knowledge pack to the payload (and chart image if attached). "
        "Return the JSON object now."
    )
    return BuiltPrompt(system=SYSTEM_INSTRUCTION, user=user)


__all__ = ["build_prompt", "BuiltPrompt", "SYSTEM_INSTRUCTION"]
