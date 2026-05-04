"""Claude Code-facing tools.

Each module has a ``main()`` and a ``__main__`` entry point so they can
be invoked from a slash command via ``python -m
fx_monitor.tools.<name>``. Tools never call any AI directly — they
prepare data, hand the prompt to Claude Code, then accept the
generated spec back and persist it. This keeps the system on the
zero-API-cost path: the AI judgement runs inside the Claude Code
subscription session that invoked the slash command.
"""

from __future__ import annotations
