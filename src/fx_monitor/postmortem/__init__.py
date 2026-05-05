"""Post-mortem analysis layer.

For each judgement that ended with a non-trivial outcome (LOSE,
NEUTRAL_MISSED), produce a structured analysis of *why* the AI was
wrong and what to do differently next time. The analyses are
mechanical (not LLM) so they are reproducible and cheap; they exist
to give the human a concrete starting point for tuning the knowledge
pack or reviewing the historical setups, not to replace human
judgement.
"""

from __future__ import annotations
