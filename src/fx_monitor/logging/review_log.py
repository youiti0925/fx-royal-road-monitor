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


def read_review_log(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSONL review log into memory.

    Bad lines are surfaced as ``{"mode": "invalid_json", "line_no": N,
    "error": ...}`` placeholders rather than raised — the report code
    must keep working even if a record was truncated mid-write.
    """
    p = Path(path)
    if not p.exists():
        return []

    records: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    records.append(data)
            except json.JSONDecodeError:
                records.append(
                    {
                        "mode": "invalid_json",
                        "line_no": i,
                        "error": "json_decode_error",
                    }
                )
    return records


__all__ = ["append_review_log", "read_review_log"]
