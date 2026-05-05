"""Hard validator for AI-authored CorpusEntry specs.

Why this exists
---------------
Earlier iterations of the corpus contained:

- Skeleton placeholder text masquerading as v7 doctrine reasoning (F1).
- Specs that listed only the legacy 14 procedure_steps even though the
  knowledge pack defines 29 (F4).
- ENTRY/STOP price pairs separated by < 1 pip on a market with ATR 2-3 pip
  — visually unreadable on a chart and impossible to execute (F5/F6).
- ScreenZone / ScreenLine / ScreenPoint with absolute archive indexes
  (e.g. 615-735) instead of window-local 0-119, blowing up the chart canvas
  to thousands of pixels (F7).
- HOLD/SUPPRESSED entries with no entry_trigger / invalidation / target
  lines, so the chart had no ENTRY ★ / STOP ✕ / TARGET ◆ markers (F9).

These slipped through because nothing in the save path *enforced*
invariants. The AI judge (Claude) wrote whatever, and the store accepted
whatever.

This validator runs synchronously inside :meth:`JsonlVectorStore.add`.
If it returns issues, the store raises and the entry is not persisted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fx_monitor.corpus.schema import CorpusEntry
from fx_monitor.live.structure_detector import (
    detect_channels,
    enumerate_trendlines,
)


_KNOWLEDGE_PACK_PATH = (
    Path(__file__).resolve().parent.parent / "ai" / "knowledge_pack_v2.json"
)
_WINDOW_SIZE = 60  # past + future = 120 total bars; valid index range = [0, 120)


def _load_knowledge_pack() -> dict[str, Any]:
    return json.loads(_KNOWLEDGE_PACK_PATH.read_text(encoding="utf-8"))


def _expected_step_keys() -> set[str]:
    return {s["key"] for s in _load_knowledge_pack().get("procedure_steps", [])}


def _is_placeholder(text: str) -> bool:
    """Detect skeleton/placeholder-ish ``result_ja`` strings."""
    if not text:
        return True
    if len(text.strip()) < 15:
        return True
    lowered = text.lower()
    bad_substrings = (
        "skeleton",
        "placeholder",
        "tbd",
        "to be done",
        "n/a",
        "not applicable",
    )
    return any(b in lowered for b in bad_substrings)


def validate_entry(entry: CorpusEntry) -> list[str]:
    """Return a list of human-readable error messages. Empty list = OK."""
    errors: list[str] = []
    spec = entry.judgement
    pack = entry.market_pack
    atr = float(getattr(pack.atr, "m5_14", 0.0) or 0.0)

    # ----- F1: no skeleton/placeholder reasoning -----
    for s in spec.procedure_steps:
        if _is_placeholder(s.result_ja):
            errors.append(
                f"F1 step '{s.key}' has placeholder/empty result_ja "
                f"(len={len(s.result_ja or '')})"
            )
        if s.label_ja == s.key or not s.label_ja:
            errors.append(
                f"F1 step '{s.key}' has missing/untranslated label_ja "
                f"(label_ja={s.label_ja!r})"
            )

    # ----- F4: doctrine coverage — every knowledge_pack step key must appear -----
    expected = _expected_step_keys()
    if expected:
        actual = {s.key for s in spec.procedure_steps}
        missing = expected - actual
        if missing:
            errors.append(
                f"F4 procedure_steps missing keys from knowledge_pack: "
                f"{sorted(missing)}"
            )

    # ----- F7: indexes must be in window-local [0, 120) range -----
    upper = _WINDOW_SIZE * 2  # 120
    for p in spec.points:
        if p.index is not None and not (0 <= p.index < upper):
            errors.append(
                f"F7 point {p.id!r} index={p.index} out of [0,{upper})"
            )
    for line in spec.lines:
        for f in ("start_index", "end_index"):
            v = getattr(line, f, None)
            if v is not None and not (0 <= v < upper):
                errors.append(
                    f"F7 line {line.id!r}.{f}={v} out of [0,{upper})"
                )
    for z in spec.zones:
        for f in ("index_low", "index_high"):
            v = getattr(z, f, None)
            if v is not None and not (0 <= v <= upper):
                errors.append(
                    f"F7 zone {z.id!r}.{f}={v} out of [0,{upper}]"
                )

    # ----- F8: at least one fully-coordinate slanted trendline -----
    slanted = [
        l
        for l in spec.lines
        if l.kind == "trendline"
        and getattr(l, "start_index", None) is not None
        and getattr(l, "end_index", None) is not None
        and getattr(l, "start_price", None) is not None
        and getattr(l, "end_price", None) is not None
    ]
    if not slanted:
        errors.append(
            "F8 no slanted trendline: spec.lines must contain ≥1 line with "
            "kind='trendline' AND start_index/end_index/start_price/end_price all set"
        )

    # ----- F9: ENTRY / STOP / TARGET lines required so chart markers render -----
    entry_l = next(
        (
            l
            for l in spec.lines
            if (l.role == "entry_trigger" or l.kind == "neckline")
            and l.price is not None
        ),
        None,
    )
    stop_l = next(
        (l for l in spec.lines if l.kind == "invalidation" and l.price is not None),
        None,
    )
    target_l = next(
        (l for l in spec.lines if l.kind == "target" and l.price is not None),
        None,
    )
    if entry_l is None:
        errors.append(
            "F9 missing entry line: spec.lines must contain a line with "
            "role='entry_trigger' OR kind='neckline' (drives ENTRY ★ marker). "
            "Use 観測ENTRY for HOLD/SUPPRESSED specs."
        )
    if stop_l is None:
        errors.append(
            "F9 missing invalidation line: spec.lines must contain a line "
            "with kind='invalidation' (drives STOP ✕ marker)"
        )
    if target_l is None:
        errors.append(
            "F9 missing target line: spec.lines must contain a line with "
            "kind='target' (drives TARGET ◆ marker)"
        )

    # ----- F5/F6: ENTRY-STOP gap >= ATR × 0.5 -----
    if entry_l is not None and stop_l is not None and atr > 0:
        gap = abs(entry_l.price - stop_l.price)
        min_gap = atr * 0.5
        if gap < min_gap:
            gap_pip = gap * 10000.0
            min_pip = min_gap * 10000.0
            errors.append(
                f"F5 ENTRY-STOP gap {gap_pip:.2f}pip < ATR×0.5 = {min_pip:.2f}pip "
                f"(entry={entry_l.price:.5f}, stop={stop_l.price:.5f}, "
                f"atr={atr*10000:.2f}pip). "
                "Stops this tight collapse the markers visually and are "
                "impractical to execute."
            )

    # ----- F15: spec must reference the strongest code-detected trendline -----
    # Aim: prevent the anchor 2 case where AI drew 2-touch TLs while a 5+
    # touch HIGH cluster TL was sitting in the pivot data.
    pivots = pack.pivots
    if pivots:
        for tl_kind in ("HIGH", "LOW"):
            code_tls = enumerate_trendlines(
                pivots, kind=tl_kind, min_touches=3, tolerance_pip=0.8,
                min_scale="swing",  # ignore micro-pivot coincidences
            )
            if not code_tls:
                continue
            top = code_tls[0]
            spec_slants = [
                l for l in spec.lines
                if l.kind == "trendline"
                and getattr(l, "start_index", None) is not None
                and getattr(l, "end_index", None) is not None
            ]
            slope_pip = lambda l: (
                (l.end_price - l.start_price) / (l.end_index - l.start_index) * 10000
                if (l.end_price is not None and l.start_price is not None
                    and l.end_index != l.start_index) else None
            )
            matched = False
            for l in spec_slants:
                s = slope_pip(l)
                if s is None:
                    continue
                if abs(s - top.slope_pip_per_bar) <= 0.3 and (
                    abs(l.start_index - top.start_index) <= 5
                    or abs(l.end_index - top.end_index) <= 5
                ):
                    matched = True
                    break
            if not matched:
                errors.append(
                    f"F15 missed strongest {tl_kind} trendline: "
                    f"{top.touch_count} touches, slope {top.slope_pip_per_bar:+.2f}pip/bar, "
                    f"idx {top.start_index}->{top.end_index} "
                    f"({top.start_price:.5f}->{top.end_price:.5f}). "
                    "AI spec did not include any matching slanted trendline."
                )

    # ----- F16: side != NEUTRAL must not coexist with a clear channel -----
    # Aim: prevent the anchor 5 case where AI called BUY/WAIT_RETEST inside
    # a rising channel (should have been NEUTRAL/WAIT_BREAKOUT).
    if pivots and spec.side != "NEUTRAL":
        channels = detect_channels(
            pivots, min_touches_per_line=3,
            parallel_tolerance_pip_per_bar=0.4,
            tolerance_pip=0.8,
            min_scale="swing",  # ignore micro-pivot coincidences
        )
        if channels:
            top_ch = channels[0]
            if top_ch.upper.touch_count + top_ch.lower.touch_count >= 7:
                errors.append(
                    f"F16 directional side={spec.side} but a {top_ch.direction} "
                    f"channel is detected (upper {top_ch.upper.touch_count}t / "
                    f"lower {top_ch.lower.touch_count}t, slope diff "
                    f"{top_ch.slope_diff_pip_per_bar:+.2f}pip/bar). "
                    "Channel-internal touches require WAIT_BREAKOUT, not BUY/SELL."
                )

    return errors


class CorpusValidationError(ValueError):
    """Raised by JsonlVectorStore.add when an entry fails validation."""

    def __init__(self, entry_id: str, issues: list[str]) -> None:
        self.entry_id = entry_id
        self.issues = list(issues)
        msg = f"corpus entry {entry_id} failed validation:\n  - " + "\n  - ".join(issues)
        super().__init__(msg)


__all__ = ["validate_entry", "CorpusValidationError"]
