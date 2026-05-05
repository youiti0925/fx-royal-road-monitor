"""Deterministic structure detection on pivot lists.

This module exists because the AI judge (a Claude session) can reliably
read sequential narratives (Dow trend, simple double top) but cannot
reliably enumerate combinatorial structures (multi-touch trendlines,
parallel channels). See ``docs/SPEC.md`` §2.A.1 / §2.B.9 for the
underlying weakness analysis and §3 F8 / F14 for past failures.

Concrete past failures this module is meant to prevent:

- F8 (anchor 2): a 5-touch descending TL through the major HIGH cluster
  (idx 10-34) was sitting in the pivot list, but the AI wrote a
  trendline using only 2 obvious pivots (idx 37→46) and missed the
  longer, more meaningful one.

- F14 (anchor 5): a rising channel with a 4-touch upper line and a
  3-touch lower line was present, but the AI called the setup
  "BUY/WAIT_RETEST" — buying at the upper edge of a rising channel.
  Outcome was LOSE.

The functions here are intentionally deterministic rule-based, not ML.
The AI is downstream of this module and consumes annotations, never the
raw enumeration; the validator (``entry_validator.py``) compares AI
output against these annotations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence


# We keep this module independent of the live.PivotPointV2 schema so it
# can also be called from tests with synthetic dicts.
@dataclass(frozen=True)
class _Pivot:
    index: int
    price: float
    kind: Literal["HIGH", "LOW"]
    scale: Literal["micro", "swing", "major"] = "micro"


def _coerce_pivots(pivots: Sequence) -> list[_Pivot]:
    """Accept either pydantic PivotPointV2 instances or dicts."""
    out: list[_Pivot] = []
    for p in pivots:
        if isinstance(p, _Pivot):
            out.append(p)
            continue
        if isinstance(p, dict):
            out.append(_Pivot(
                index=p["index"], price=p["price"],
                kind=p["kind"], scale=p.get("scale", "micro"),
            ))
        else:
            out.append(_Pivot(
                index=getattr(p, "index"), price=getattr(p, "price"),
                kind=getattr(p, "kind"), scale=getattr(p, "scale", "micro"),
            ))
    return sorted(out, key=lambda p: p.index)


# ---------------------------------------------------------------------------
# Trendline enumeration (F8 countermeasure)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrendlineCandidate:
    """A line through 3+ pivots of the same kind (HIGH or LOW)."""
    kind: Literal["HIGH", "LOW"]
    slope_pip_per_bar: float          # positive = ascending
    intercept_price: float             # price at index=0
    touches: tuple[tuple[int, float], ...]  # (index, price) tuples on the line
    start_index: int
    end_index: int
    start_price: float
    end_price: float

    @property
    def touch_count(self) -> int:
        return len(self.touches)

    @property
    def duration(self) -> int:
        return self.end_index - self.start_index


def enumerate_trendlines(
    pivots: Sequence,
    *,
    kind: Literal["HIGH", "LOW"],
    min_touches: int = 3,
    tolerance_pip: float = 1.0,
    pip_size: float = 0.0001,
    min_scale: Literal["micro", "swing", "major"] = "micro",
) -> list[TrendlineCandidate]:
    """Enumerate trendlines through ``min_touches`` or more same-kind pivots.

    Algorithm
    ---------
    1. Filter pivots by ``kind`` and ``min_scale``.
    2. For every (i, j) pair with i < j, compute slope and intercept.
    3. Count how many pivots fall within ``tolerance_pip`` of that line.
    4. Keep candidates with ``touch_count >= min_touches``.
    5. Deduplicate near-identical lines (slope close, anchor-set overlap).
    6. Sort by ``score = touch_count * duration`` descending.

    Notes on parameters
    -------------------
    ``tolerance_pip = 1.0`` means a pivot is "on the line" if its price is
    within 1 pip of the line at that index. For M5 EUR/USD with ATR ~2-3
    pip this is approximately ATR × 0.4 — tight enough to be meaningful,
    loose enough to absorb noise.
    """
    pool = [
        p for p in _coerce_pivots(pivots)
        if p.kind == kind and _scale_at_least(p.scale, min_scale)
    ]
    n = len(pool)
    if n < min_touches:
        return []

    tol = tolerance_pip * pip_size
    candidates: list[TrendlineCandidate] = []

    for i in range(n):
        for j in range(i + 1, n):
            p1, p2 = pool[i], pool[j]
            if p2.index == p1.index:
                continue
            slope = (p2.price - p1.price) / (p2.index - p1.index)
            intercept = p1.price - slope * p1.index

            on_line = []
            for p in pool:
                expected = intercept + slope * p.index
                if abs(p.price - expected) <= tol:
                    on_line.append((p.index, p.price))
            if len(on_line) < min_touches:
                continue

            on_line_sorted = tuple(sorted(on_line, key=lambda t: t[0]))
            cand = TrendlineCandidate(
                kind=kind,
                slope_pip_per_bar=slope / pip_size,
                intercept_price=intercept,
                touches=on_line_sorted,
                start_index=on_line_sorted[0][0],
                end_index=on_line_sorted[-1][0],
                start_price=on_line_sorted[0][1],
                end_price=on_line_sorted[-1][1],
            )
            candidates.append(cand)

    return _dedupe_trendlines(candidates)


def _dedupe_trendlines(
    candidates: list[TrendlineCandidate],
    slope_tol: float = 0.05,
) -> list[TrendlineCandidate]:
    """Merge near-duplicate candidates (same slope band, overlapping touches).

    Sort by touch_count desc then duration desc, then for each candidate
    drop later ones whose anchor set is a subset of an already-kept one.
    """
    candidates_sorted = sorted(
        candidates, key=lambda c: (c.touch_count, c.duration), reverse=True
    )
    kept: list[TrendlineCandidate] = []
    for c in candidates_sorted:
        c_indexes = {t[0] for t in c.touches}
        is_subset = False
        for k in kept:
            if abs(k.slope_pip_per_bar - c.slope_pip_per_bar) > slope_tol:
                continue
            k_indexes = {t[0] for t in k.touches}
            if c_indexes.issubset(k_indexes):
                is_subset = True
                break
        if not is_subset:
            kept.append(c)
    return kept


_SCALE_RANK = {"micro": 0, "swing": 1, "major": 2}


def _scale_at_least(scale: str, minimum: str) -> bool:
    return _SCALE_RANK.get(scale, 0) >= _SCALE_RANK.get(minimum, 0)


# ---------------------------------------------------------------------------
# Channel detection (F14 countermeasure)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChannelCandidate:
    """Two parallel-ish trendlines (one HIGH, one LOW)."""
    upper: TrendlineCandidate
    lower: TrendlineCandidate
    direction: Literal["rising", "falling", "horizontal"]
    slope_diff_pip_per_bar: float

    @property
    def width_pip_at_start(self) -> float:
        return (self.upper.start_price - self.lower.start_price) * 10000.0

    @property
    def width_pip_at_end(self) -> float:
        return (self.upper.end_price - self.lower.end_price) * 10000.0


def detect_channels(
    pivots: Sequence,
    *,
    min_touches_per_line: int = 3,
    parallel_tolerance_pip_per_bar: float = 0.5,
    pip_size: float = 0.0001,
    tolerance_pip: float = 1.0,
) -> list[ChannelCandidate]:
    """Detect channels = pair of parallel-ish trendlines (one HIGH, one LOW).

    For every (high TL, low TL) pair, accept as channel if their slopes
    differ by less than ``parallel_tolerance_pip_per_bar`` and they overlap
    in time (their index ranges intersect for at least 5 bars).
    """
    high_tls = enumerate_trendlines(
        pivots, kind="HIGH",
        min_touches=min_touches_per_line,
        tolerance_pip=tolerance_pip, pip_size=pip_size,
    )
    low_tls = enumerate_trendlines(
        pivots, kind="LOW",
        min_touches=min_touches_per_line,
        tolerance_pip=tolerance_pip, pip_size=pip_size,
    )
    channels: list[ChannelCandidate] = []
    for h in high_tls:
        for l in low_tls:
            if abs(h.slope_pip_per_bar - l.slope_pip_per_bar) > parallel_tolerance_pip_per_bar:
                continue
            overlap_lo = max(h.start_index, l.start_index)
            overlap_hi = min(h.end_index, l.end_index)
            if overlap_hi - overlap_lo < 5:
                continue
            avg_slope = (h.slope_pip_per_bar + l.slope_pip_per_bar) / 2
            if avg_slope > 0.1:
                direction = "rising"
            elif avg_slope < -0.1:
                direction = "falling"
            else:
                direction = "horizontal"
            channels.append(ChannelCandidate(
                upper=h, lower=l, direction=direction,
                slope_diff_pip_per_bar=h.slope_pip_per_bar - l.slope_pip_per_bar,
            ))
    # Dedup: keep top-1 per direction by combined touch count
    channels.sort(
        key=lambda c: (c.upper.touch_count + c.lower.touch_count, c.upper.duration),
        reverse=True,
    )
    return channels


# ---------------------------------------------------------------------------
# Pattern detection (sequential, AI fallback)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatternHit:
    name: str  # "double_top" / "double_bottom" / "head_and_shoulders" / etc.
    pivots_idx: tuple[int, ...]
    confidence: float


def detect_double_top(
    pivots: Sequence,
    *,
    height_tolerance_pip: float = 1.0,
    pip_size: float = 0.0001,
    min_separation_bars: int = 5,
) -> PatternHit | None:
    """Detect double top: 2 highs at similar height with a low between.

    Doctrinal definition (knowledge_pack v7 glossary "ダブルトップ"):
    - 2 HIGH pivots at the same level (±ATR×0.5 ≈ 1 pip on M5 EUR/USD)
    - A LOW between them
    - Separation of at least a few bars
    """
    pool = _coerce_pivots(pivots)
    highs = [p for p in pool if p.kind == "HIGH" and p.scale in ("swing", "major")]
    lows = [p for p in pool if p.kind == "LOW" and p.scale in ("swing", "major")]

    tol = height_tolerance_pip * pip_size
    best: PatternHit | None = None
    best_score = 0.0
    for i in range(len(highs)):
        for j in range(i + 1, len(highs)):
            h1, h2 = highs[i], highs[j]
            if h2.index - h1.index < min_separation_bars:
                continue
            if abs(h1.price - h2.price) > tol:
                continue
            # Find a LOW between
            between = [l for l in lows if h1.index < l.index < h2.index]
            if not between:
                continue
            neck = min(between, key=lambda l: l.price)
            depth_pip = (h1.price - neck.price) / pip_size
            if depth_pip < 2.0:  # too shallow
                continue
            score = depth_pip * (1.0 - abs(h1.price - h2.price) / tol)
            if score > best_score:
                best_score = score
                best = PatternHit(
                    name="double_top",
                    pivots_idx=(h1.index, neck.index, h2.index),
                    confidence=min(0.95, 0.5 + 0.05 * depth_pip),
                )
    return best


def detect_double_bottom(
    pivots: Sequence,
    *,
    height_tolerance_pip: float = 1.0,
    pip_size: float = 0.0001,
    min_separation_bars: int = 5,
) -> PatternHit | None:
    """Mirror of detect_double_top for LOW pivots."""
    pool = _coerce_pivots(pivots)
    highs = [p for p in pool if p.kind == "HIGH" and p.scale in ("swing", "major")]
    lows = [p for p in pool if p.kind == "LOW" and p.scale in ("swing", "major")]
    tol = height_tolerance_pip * pip_size
    best: PatternHit | None = None
    best_score = 0.0
    for i in range(len(lows)):
        for j in range(i + 1, len(lows)):
            l1, l2 = lows[i], lows[j]
            if l2.index - l1.index < min_separation_bars:
                continue
            if abs(l1.price - l2.price) > tol:
                continue
            between = [h for h in highs if l1.index < h.index < l2.index]
            if not between:
                continue
            neck = max(between, key=lambda h: h.price)
            depth_pip = (neck.price - l1.price) / pip_size
            if depth_pip < 2.0:
                continue
            score = depth_pip * (1.0 - abs(l1.price - l2.price) / tol)
            if score > best_score:
                best_score = score
                best = PatternHit(
                    name="double_bottom",
                    pivots_idx=(l1.index, neck.index, l2.index),
                    confidence=min(0.95, 0.5 + 0.05 * depth_pip),
                )
    return best


def detect_head_and_shoulders(
    pivots: Sequence,
    *,
    head_higher_pip: float = 2.0,
    shoulder_tolerance_pip: float = 2.0,
    pip_size: float = 0.0001,
) -> PatternHit | None:
    """Detect 3-peak H&S: shoulders at similar height, head distinctly higher.

    Doctrinal definition: left shoulder, head (higher than both shoulders by
    ≥ ATR×1.0), right shoulder, with neck = lowest LOW between.
    """
    pool = _coerce_pivots(pivots)
    highs = [p for p in pool if p.kind == "HIGH" and p.scale in ("swing", "major")]
    lows = [p for p in pool if p.kind == "LOW"]
    head_min_diff = head_higher_pip * pip_size
    shoulder_tol = shoulder_tolerance_pip * pip_size
    best: PatternHit | None = None
    best_score = 0.0
    for i in range(len(highs)):
        for j in range(i + 1, len(highs)):
            for k in range(j + 1, len(highs)):
                ls, head, rs = highs[i], highs[j], highs[k]
                if not (head.price - ls.price >= head_min_diff
                        and head.price - rs.price >= head_min_diff):
                    continue
                if abs(ls.price - rs.price) > shoulder_tol:
                    continue
                # Neck = lowest LOW between LS-Head and Head-RS
                neck_pool = [l for l in lows if ls.index < l.index < rs.index]
                if not neck_pool:
                    continue
                score = (head.price - max(ls.price, rs.price)) / pip_size
                if score > best_score:
                    best_score = score
                    neck_lo = min(neck_pool, key=lambda l: l.price)
                    best = PatternHit(
                        name="head_and_shoulders",
                        pivots_idx=(ls.index, head.index, rs.index, neck_lo.index),
                        confidence=min(0.9, 0.4 + 0.05 * score),
                    )
    return best


def detect_triangle(
    pivots: Sequence,
    *,
    min_touches_per_line: int = 3,
    convergence_threshold: float = 0.3,
    pip_size: float = 0.0001,
) -> PatternHit | None:
    """Detect ascending / descending / symmetric triangle.

    Triangle = upper TL and lower TL converging (slopes opposite signs OR
    one flat with the other angled).
    """
    high_tls = enumerate_trendlines(
        pivots, kind="HIGH", min_touches=min_touches_per_line, pip_size=pip_size,
    )
    low_tls = enumerate_trendlines(
        pivots, kind="LOW", min_touches=min_touches_per_line, pip_size=pip_size,
    )
    if not high_tls or not low_tls:
        return None
    h, l = high_tls[0], low_tls[0]
    # Convergence: slopes pointing toward each other
    converging = (
        (h.slope_pip_per_bar < -convergence_threshold and l.slope_pip_per_bar > convergence_threshold)
        or (abs(h.slope_pip_per_bar) < convergence_threshold and l.slope_pip_per_bar > convergence_threshold)  # ascending
        or (h.slope_pip_per_bar < -convergence_threshold and abs(l.slope_pip_per_bar) < convergence_threshold)  # descending
    )
    if not converging:
        return None
    if abs(h.slope_pip_per_bar) < convergence_threshold:
        kind = "ascending_triangle"
    elif abs(l.slope_pip_per_bar) < convergence_threshold:
        kind = "descending_triangle"
    else:
        kind = "symmetric_triangle"
    return PatternHit(
        name=kind,
        pivots_idx=tuple(t[0] for t in h.touches) + tuple(t[0] for t in l.touches),
        confidence=0.6,
    )


# ---------------------------------------------------------------------------
# Dow state (sequential rules)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DowState:
    state: Literal["HH-HL", "LH-LL", "range", "broken"]
    swing_highs: tuple[float, ...]
    swing_lows: tuple[float, ...]
    reason: str


def detect_dow_state(pivots: Sequence) -> DowState:
    """Identify Dow theory trend state from sequence of swing pivots."""
    pool = _coerce_pivots(pivots)
    swing_highs = [p for p in pool if p.kind == "HIGH" and p.scale in ("swing", "major")]
    swing_lows = [p for p in pool if p.kind == "LOW" and p.scale in ("swing", "major")]
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return DowState(
            "range",
            tuple(p.price for p in swing_highs),
            tuple(p.price for p in swing_lows),
            "insufficient swing pivots",
        )
    # Use last 3 of each
    h_vals = [p.price for p in swing_highs[-3:]]
    l_vals = [p.price for p in swing_lows[-3:]]
    # Strict inequality: equal values don't count as rising/falling.
    rising_highs = (
        all(h_vals[i] <= h_vals[i + 1] for i in range(len(h_vals) - 1))
        and h_vals[0] < h_vals[-1]
    )
    falling_highs = (
        all(h_vals[i] >= h_vals[i + 1] for i in range(len(h_vals) - 1))
        and h_vals[0] > h_vals[-1]
    )
    rising_lows = (
        all(l_vals[i] <= l_vals[i + 1] for i in range(len(l_vals) - 1))
        and l_vals[0] < l_vals[-1]
    )
    falling_lows = (
        all(l_vals[i] >= l_vals[i + 1] for i in range(len(l_vals) - 1))
        and l_vals[0] > l_vals[-1]
    )
    if rising_highs and rising_lows:
        return DowState("HH-HL", tuple(h_vals), tuple(l_vals), "ascending swings")
    if falling_highs and falling_lows:
        return DowState("LH-LL", tuple(h_vals), tuple(l_vals), "descending swings")
    return DowState("range", tuple(h_vals), tuple(l_vals), "mixed swings")


# ---------------------------------------------------------------------------
# Top-level summary (for AI prompt embedding)
# ---------------------------------------------------------------------------


@dataclass
class StructureSummary:
    trendlines_high: list[TrendlineCandidate] = field(default_factory=list)
    trendlines_low: list[TrendlineCandidate] = field(default_factory=list)
    channels: list[ChannelCandidate] = field(default_factory=list)
    double_top: PatternHit | None = None
    double_bottom: PatternHit | None = None
    head_and_shoulders: PatternHit | None = None
    triangle: PatternHit | None = None
    dow: DowState | None = None

    def to_text_annotation(self) -> str:
        """Render annotation for embedding in AI prompt."""
        lines: list[str] = ["[code-detected structure]"]
        # TLs
        if self.trendlines_high:
            for tl in self.trendlines_high[:3]:
                lines.append(
                    f"  HIGH TL: {tl.touch_count} touches, slope {tl.slope_pip_per_bar:+.2f} pip/bar, "
                    f"idx {tl.start_index}->{tl.end_index}"
                )
        else:
            lines.append("  HIGH TL: none with >=3 touches")
        if self.trendlines_low:
            for tl in self.trendlines_low[:3]:
                lines.append(
                    f"  LOW TL: {tl.touch_count} touches, slope {tl.slope_pip_per_bar:+.2f} pip/bar, "
                    f"idx {tl.start_index}->{tl.end_index}"
                )
        else:
            lines.append("  LOW TL: none with >=3 touches")
        # Channels
        if self.channels:
            for ch in self.channels[:2]:
                lines.append(
                    f"  Channel ({ch.direction}): upper {ch.upper.touch_count}t/lower {ch.lower.touch_count}t, "
                    f"slope diff {ch.slope_diff_pip_per_bar:+.2f} pip/bar"
                )
        else:
            lines.append("  Channel: not detected")
        # Patterns
        for nm, hit in (
            ("double_top", self.double_top),
            ("double_bottom", self.double_bottom),
            ("head_and_shoulders", self.head_and_shoulders),
            ("triangle", self.triangle),
        ):
            if hit:
                lines.append(f"  Pattern: {hit.name} (conf {hit.confidence:.2f})")
        # Dow
        if self.dow:
            lines.append(f"  Dow: {self.dow.state} ({self.dow.reason})")
        return "\n".join(lines)


def summarize_structure(pivots: Sequence) -> StructureSummary:
    """One-shot wrapper that runs all detectors. Useful for AI prompt + validator."""
    return StructureSummary(
        trendlines_high=enumerate_trendlines(pivots, kind="HIGH", min_touches=3),
        trendlines_low=enumerate_trendlines(pivots, kind="LOW", min_touches=3),
        channels=detect_channels(pivots),
        double_top=detect_double_top(pivots),
        double_bottom=detect_double_bottom(pivots),
        head_and_shoulders=detect_head_and_shoulders(pivots),
        triangle=detect_triangle(pivots),
        dow=detect_dow_state(pivots),
    )


__all__ = [
    "TrendlineCandidate",
    "ChannelCandidate",
    "PatternHit",
    "DowState",
    "StructureSummary",
    "enumerate_trendlines",
    "detect_channels",
    "detect_double_top",
    "detect_double_bottom",
    "detect_head_and_shoulders",
    "detect_triangle",
    "detect_dow_state",
    "summarize_structure",
]
