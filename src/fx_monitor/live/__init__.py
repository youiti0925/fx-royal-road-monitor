"""Live observation-only layer.

This package implements the live judgment pipeline. It is **observation-only**:
no order placement, no broker integration, no notification dispatch.

Loading this package runs an import-time safety guard
(:mod:`fx_monitor.live.safety_guard`) that fails fast if forbidden modules
have been imported into the same Python process.
"""

from __future__ import annotations

# Run the import-time guard. Importing the module is sufficient: it executes
# the guard at module-load time. We re-export the function for explicit calls
# in tests.
from .safety_guard import assert_safe_environment

__all__ = ["assert_safe_environment"]

# Trigger the guard once at package load.
assert_safe_environment()
