"""Corpus layer: past judgement + outcome storage and retrieval.

Used by both the offline batch (writes historical entries) and the live
loop (writes new judgements, retrieves similar past entries). Storage
is intentionally dependency-light — a JSONL file plus a numpy memmap of
vectors — so the system runs with zero external services.
"""

from __future__ import annotations
