"""Build the AI review prompt.

Per AI_REVIEW_POLICY.md, every call must include the *full* knowledge pack,
the JSON schema, and the structured payload. We do not trim. Optimization
(prompt caching) is the API's job, not ours.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.models import ChartPayload
from ..knowledge.loader import KnowledgePack
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


def build_prompt(payload: ChartPayload, pack: KnowledgePack) -> BuiltPrompt:
    payload_json = payload.model_dump_json(indent=2)
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
