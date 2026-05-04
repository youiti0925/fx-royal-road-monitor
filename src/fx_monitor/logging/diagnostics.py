"""Write a diagnostics JSON artifact for offline inspection of a run.

Goals:

- Record what feed / draft / AI / decision / safety looked like.
- Never expose secrets — keys whose name suggests they hold a credential
  (``api_key``, ``token``, ``secret``, ``webhook``, ...) are redacted
  recursively before write.
- Never store prompt text or raw payload bodies (the caller is
  responsible for not putting those in ``data``; the redaction here is
  a belt-and-suspenders layer).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FORBIDDEN_DIAGNOSTIC_KEYS = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DISCORD_WEBHOOK_URL",
    "LINE_NOTIFY_TOKEN",
    "api_key",
    "webhook",
    "token",
    "secret",
}

_NEEDLES = ("api_key", "token", "secret", "webhook")
_REDACTED = "***redacted***"


def _is_secret_key(key: str) -> bool:
    if key in FORBIDDEN_DIAGNOSTIC_KEYS:
        return True
    lower = key.lower()
    return any(needle in lower for needle in _NEEDLES)


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            if _is_secret_key(key):
                out[key] = _REDACTED
            else:
                out[key] = _sanitize(v)
        return out

    if isinstance(value, list):
        return [_sanitize(x) for x in value]

    if isinstance(value, datetime):
        return value.isoformat()

    return value


def write_diagnostics(
    *,
    path: str | Path,
    data: dict[str, Any],
) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "diagnostics_schema": "fx_monitor_diagnostics_v1",
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
        **_sanitize(data),
    }

    p.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return p


__all__ = ["write_diagnostics", "FORBIDDEN_DIAGNOSTIC_KEYS"]
