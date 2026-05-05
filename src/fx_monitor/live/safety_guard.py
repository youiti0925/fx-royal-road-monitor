"""Import-time safety guard for the live observation-only layer.

This module enforces the safety perimeter at process load time. If any
forbidden broker / live-trading / order-execution module has been imported
into the current Python process, importing :mod:`fx_monitor.live` will raise
:class:`UnsafeEnvironmentError` and refuse to proceed.

The guard is intentionally cheap (a substring scan over ``sys.modules`` keys)
so it can run on every import without measurable overhead.
"""

from __future__ import annotations

import sys

__all__ = ["UnsafeEnvironmentError", "assert_safe_environment", "FORBIDDEN_SUBSTRINGS"]


class UnsafeEnvironmentError(RuntimeError):
    """Raised when the live layer detects a forbidden module in the process."""


FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "oanda",
    "paper_broker",
    "paper_trade",
    "live_order",
    "place_order",
    "broker_api",
    "execute_trade",
)


def _scan_loaded_modules(loaded: dict[str, object] | None = None) -> list[str]:
    if loaded is None:
        loaded = sys.modules
    hits: list[str] = []
    for name in loaded:
        lower = name.lower()
        for forbidden in FORBIDDEN_SUBSTRINGS:
            if forbidden in lower:
                hits.append(name)
                break
    return hits


def assert_safe_environment() -> None:
    """Raise if any forbidden module has been imported into the current process.

    The check is conservative: a substring match against
    :data:`FORBIDDEN_SUBSTRINGS` is enough to reject. We never attempt to
    "clean up" an offending import — observation-only systems must abort
    rather than continue with mixed state.
    """
    hits = _scan_loaded_modules()
    if hits:
        raise UnsafeEnvironmentError(
            "live layer refuses to load: forbidden module(s) present in process: "
            + ", ".join(sorted(hits))
        )
