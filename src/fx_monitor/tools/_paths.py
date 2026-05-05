"""Shared path helpers for the tool layer."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(os.environ.get("FX_MONITOR_ROOT", Path.cwd())).resolve()


def data_root() -> Path:
    return repo_root() / "data"


def corpus_root(name: str = "default") -> Path:
    return data_root() / "corpus" / name


def progress_path(symbol: str, timeframe: str) -> Path:
    safe = symbol.replace("=", "_").replace("/", "_")
    return data_root() / "progress" / f"{safe}_{timeframe}.json"


def replay_log_path() -> Path:
    return data_root() / "replay_log" / "replay.jsonl"


def pending_judgement_path(entry_id: str) -> Path:
    return data_root() / "pending_judgements" / f"{entry_id}.json"


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


__all__ = [
    "repo_root",
    "data_root",
    "corpus_root",
    "progress_path",
    "replay_log_path",
    "pending_judgement_path",
    "ensure_parent",
]
