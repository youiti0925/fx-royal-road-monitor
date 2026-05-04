"""Append-only JSONL review log.

Used by the draft AI review path: each call writes one line summarizing the
draft + reviewer output for offline inspection. By policy this log must NOT
contain prompts, raw payloads, or API keys — only structured summary fields.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def append_review_log(
    *,
    path: str | Path,
    record: dict[str, Any],
) -> Path:
    """Append one JSONL record. Creates parent directories as needed.

    The caller is responsible for not putting secrets / prompts / raw
    payloads into ``record``. We do not strip or redact here — that's a
    contract, not a feature, so a future test can pin it.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    safe_record = {
        "logged_at_utc": datetime.now(timezone.utc).isoformat(),
        **record,
    }

    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(safe_record, ensure_ascii=False, default=_json_default))
        f.write("\n")

    return p


__all__ = ["append_review_log"]
