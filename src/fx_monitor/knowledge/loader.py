"""Load the royal-road knowledge pack from disk.

The knowledge pack is shipped as raw markdown and embedded *verbatim* into
each AI prompt. We deliberately do not summarize or trim it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = "docs/ROYAL_ROAD_KNOWLEDGE_PACK_v1.md"


@dataclass(frozen=True)
class KnowledgePack:
    path: Path
    version: str
    text: str

    def __len__(self) -> int:
        return len(self.text)


def _detect_version(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# ") and "v" in s.lower():
            return s.lstrip("# ").strip()
    return "unknown"


def load_knowledge_pack(path: str | os.PathLike[str] | None = None) -> KnowledgePack:
    p = Path(path or os.environ.get("KNOWLEDGE_PACK_PATH", DEFAULT_PATH))
    if not p.is_absolute():
        # Resolve against CWD; in production this is the repo root.
        p = Path.cwd() / p
    if not p.exists():
        raise FileNotFoundError(f"Knowledge pack not found at {p}")
    text = p.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Knowledge pack at {p} is empty")
    return KnowledgePack(path=p, version=_detect_version(text), text=text)


__all__ = ["KnowledgePack", "load_knowledge_pack", "DEFAULT_PATH"]
