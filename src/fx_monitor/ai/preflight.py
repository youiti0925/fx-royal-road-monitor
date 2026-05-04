"""AI-authored MVP1 preview preflight check.

Run BEFORE the build_preview pipeline starts in ai-authored mode so a
missing API key or disabled provider produces a fast, obvious failure
instead of silently committing a placeholder preview.

Pure function; no I/O, no network. Tests pass an explicit env dict.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AiPreviewPreflightResult:
    ok: bool
    openai_ready: bool
    claude_ready: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": "ai_preview_preflight_v1",
            "ok": self.ok,
            "openai_ready": self.openai_ready,
            "claude_ready": self.claude_ready,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _truthy(value: object) -> bool:
    return str(value or "").lower() in {"1", "true", "yes"}


def check_ai_authored_preview_preflight(
    env: dict[str, str] | None = None,
) -> AiPreviewPreflightResult:
    """Decide whether the env is ready for an ai-authored preview run.

    Errors fail the run. Warnings are surfaced but do not fail; e.g. a
    key is present but ENABLED isn't explicitly set — build_preview
    will default-enable in that case.
    """
    env = dict(os.environ) if env is None else dict(env)

    errors: list[str] = []
    warnings: list[str] = []

    openai_key = bool(env.get("OPENAI_API_KEY"))
    claude_key = bool(env.get("ANTHROPIC_API_KEY"))
    openai_enabled = _truthy(env.get("OPENAI_ENABLED"))
    claude_enabled = _truthy(env.get("ANTHROPIC_ENABLED"))

    if not openai_key:
        errors.append("OPENAI_API_KEY_missing")
    if not claude_key:
        errors.append("ANTHROPIC_API_KEY_missing")

    if openai_key and not openai_enabled:
        warnings.append("OPENAI_ENABLED_not_true")
    if claude_key and not claude_enabled:
        warnings.append("ANTHROPIC_ENABLED_not_true")

    return AiPreviewPreflightResult(
        ok=not errors,
        openai_ready=openai_key,
        claude_ready=claude_key,
        errors=errors,
        warnings=warnings,
    )


__all__ = [
    "AiPreviewPreflightResult",
    "check_ai_authored_preview_preflight",
]
