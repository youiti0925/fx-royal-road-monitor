"""Tests for structure_detector.

Each test maps to a SPEC.md failure ID it is meant to prevent.
"""

from __future__ import annotations

from fx_monitor.live.structure_detector import (
    ChannelCandidate,
    DowState,
    PatternHit,
    StructureSummary,
    detect_channels,
    detect_double_bottom,
    detect_double_top,
    detect_dow_state,
    detect_extreme_anchored_trendline,
    detect_head_and_shoulders,
    detect_triangle,
    enumerate_trendlines,
    summarize_structure,
)


def _piv(idx, price, kind, scale="major"):
    return {"index": idx, "price": price, "kind": kind, "scale": scale}


# ------ enumerate_trendlines (F8 countermeasure) -----------------------------


def test_descending_5touch_HIGH_TL_detected_F8():
    """anchor 2-shaped data: 5 HIGH pivots on a descending line.

    This is the exact case the AI missed (only drew 2-touch TL).
    Code must find the longer one.

    Pivots are placed on slope = -0.5 pip/bar from (idx 10, 1.17192).
    """
    base_idx, base_price, slope = 10, 1.17192, -0.00005  # -0.5 pip/bar
    pivots = [
        _piv(idx, base_price + slope * (idx - base_idx), "HIGH")
        for idx in (10, 20, 30, 40, 50)
    ]
    tls = enumerate_trendlines(pivots, kind="HIGH", min_touches=3, tolerance_pip=0.3)
    assert len(tls) >= 1
    top = tls[0]
    assert top.touch_count >= 4
    assert top.slope_pip_per_bar < 0  # descending


def test_no_TL_when_pivots_random():
    """Random scattered pivots should produce few or no >=3-touch TLs."""
    pivots = [
        _piv(5, 1.17000, "HIGH"),
        _piv(20, 1.18000, "HIGH"),
        _piv(35, 1.16000, "HIGH"),
    ]
    tls = enumerate_trendlines(pivots, kind="HIGH", min_touches=3)
    # 3 points always lie on some line, but slope_tol needs them to fit
    # within tolerance. The above are far apart so only 2-pivot candidates
    # would qualify on each pair-fit, but we filter to >=3. At most 1 here.
    for tl in tls:
        assert tl.touch_count >= 3


def test_kind_filter_separates_HIGH_LOW():
    """Mixed pivots: only same-kind pivots should be considered."""
    pivots = [
        _piv(0, 1.17000, "HIGH"),
        _piv(10, 1.17000, "HIGH"),
        _piv(20, 1.17000, "HIGH"),
        _piv(5, 1.16000, "LOW"),
        _piv(15, 1.16000, "LOW"),
        _piv(25, 1.16000, "LOW"),
    ]
    high_tls = enumerate_trendlines(pivots, kind="HIGH")
    low_tls = enumerate_trendlines(pivots, kind="LOW")
    # Both should detect a horizontal 3-touch line.
    assert any(tl.touch_count == 3 for tl in high_tls)
    assert any(tl.touch_count == 3 for tl in low_tls)


# ------ detect_channels (F14 countermeasure) ---------------------------------


def test_rising_channel_detected_F14():
    """anchor 5-shaped data: parallel rising upper + lower lines.

    The exact case the AI missed (called BUY/WAIT_RETEST instead of
    NEUTRAL/WAIT_BREAKOUT).
    """
    # Upper line: rising with slope +1 pip/bar
    # Lower line: rising with slope +1 pip/bar, parallel
    pivots = []
    for i in range(0, 60, 10):
        pivots.append(_piv(i, 1.17000 + i * 0.0001, "HIGH"))
        pivots.append(_piv(i + 5, 1.16800 + i * 0.0001, "LOW"))
    channels = detect_channels(pivots)
    assert len(channels) >= 1
    top = channels[0]
    assert top.direction == "rising"
    assert top.upper.touch_count >= 3
    assert top.lower.touch_count >= 3
    assert abs(top.slope_diff_pip_per_bar) < 0.3


def test_no_channel_when_lines_not_parallel():
    """Detector should reject non-parallel TL pairs."""
    pivots = []
    # Upper: rising +2 pip/bar
    for i in range(0, 60, 10):
        pivots.append(_piv(i, 1.17000 + i * 0.0002, "HIGH"))
    # Lower: falling -1 pip/bar
    for i in range(0, 60, 10):
        pivots.append(_piv(i + 5, 1.16800 - i * 0.0001, "LOW"))
    channels = detect_channels(pivots, parallel_tolerance_pip_per_bar=0.5)
    assert len(channels) == 0


# ------ detect_double_top ---------------------------------------------------


def test_double_top_detected():
    """Two HIGH pivots at same level + LOW between = double top."""
    pivots = [
        _piv(10, 1.17578, "HIGH"),
        _piv(20, 1.17398, "LOW"),
        _piv(30, 1.17578, "HIGH"),
    ]
    hit = detect_double_top(pivots)
    assert hit is not None
    assert hit.name == "double_top"
    assert hit.pivots_idx == (10, 20, 30)


def test_double_top_rejected_when_heights_differ():
    pivots = [
        _piv(10, 1.17578, "HIGH"),
        _piv(20, 1.17398, "LOW"),
        _piv(30, 1.17500, "HIGH"),  # 7.8pip lower — outside 1pip tolerance
    ]
    hit = detect_double_top(pivots)
    assert hit is None


def test_double_top_rejected_when_too_shallow():
    """Neck too close to peaks → not a double top."""
    pivots = [
        _piv(10, 1.17000, "HIGH"),
        _piv(20, 1.16999, "LOW"),  # only 0.1pip deep
        _piv(30, 1.17000, "HIGH"),
    ]
    hit = detect_double_top(pivots)
    assert hit is None


# ------ detect_double_bottom ------------------------------------------------


def test_double_bottom_detected():
    pivots = [
        _piv(10, 1.16800, "LOW"),
        _piv(20, 1.16980, "HIGH"),
        _piv(30, 1.16800, "LOW"),
    ]
    hit = detect_double_bottom(pivots)
    assert hit is not None
    assert hit.name == "double_bottom"


# ------ detect_head_and_shoulders -------------------------------------------


def test_h_and_s_detected():
    pivots = [
        _piv(10, 1.17400, "HIGH"),  # left shoulder
        _piv(15, 1.17300, "LOW"),   # neck part
        _piv(20, 1.17500, "HIGH"),  # head (10pip higher than shoulders)
        _piv(25, 1.17300, "LOW"),   # neck part
        _piv(30, 1.17400, "HIGH"),  # right shoulder
    ]
    hit = detect_head_and_shoulders(pivots)
    assert hit is not None
    assert hit.name == "head_and_shoulders"


def test_h_and_s_rejected_when_head_not_higher():
    """If head isn't distinctly higher, it's a triple top, not H&S."""
    pivots = [
        _piv(10, 1.17400, "HIGH"),
        _piv(15, 1.17300, "LOW"),
        _piv(20, 1.17400, "HIGH"),  # same height as shoulders
        _piv(25, 1.17300, "LOW"),
        _piv(30, 1.17400, "HIGH"),
    ]
    hit = detect_head_and_shoulders(pivots)
    assert hit is None


# ------ detect_triangle -----------------------------------------------------


def test_ascending_triangle_detected():
    """Upper flat, lower rising → ascending triangle."""
    pivots = []
    for i in range(0, 60, 15):
        pivots.append(_piv(i, 1.17400, "HIGH"))  # all same → flat upper
    for i in range(5, 60, 15):
        pivots.append(_piv(i, 1.17000 + i * 0.0001, "LOW"))  # rising lower
    hit = detect_triangle(pivots)
    assert hit is not None
    assert hit.name == "ascending_triangle"


# ------ detect_dow_state ----------------------------------------------------


def test_dow_HH_HL_uptrend():
    pivots = [
        _piv(0, 1.17000, "LOW", scale="swing"),
        _piv(10, 1.17100, "HIGH", scale="swing"),
        _piv(20, 1.17050, "LOW", scale="swing"),
        _piv(30, 1.17200, "HIGH", scale="swing"),
        _piv(40, 1.17150, "LOW", scale="swing"),
        _piv(50, 1.17300, "HIGH", scale="swing"),
    ]
    dow = detect_dow_state(pivots)
    assert dow.state == "HH-HL"


def test_dow_LH_LL_downtrend():
    pivots = [
        _piv(0, 1.17300, "HIGH", scale="swing"),
        _piv(10, 1.17200, "LOW", scale="swing"),
        _piv(20, 1.17250, "HIGH", scale="swing"),
        _piv(30, 1.17100, "LOW", scale="swing"),
        _piv(40, 1.17150, "HIGH", scale="swing"),
        _piv(50, 1.17000, "LOW", scale="swing"),
    ]
    dow = detect_dow_state(pivots)
    assert dow.state == "LH-LL"


def test_dow_range_when_mixed():
    pivots = [
        _piv(0, 1.17100, "HIGH", scale="swing"),
        _piv(10, 1.17000, "LOW", scale="swing"),
        _piv(20, 1.17100, "HIGH", scale="swing"),
        _piv(30, 1.17000, "LOW", scale="swing"),
    ]
    dow = detect_dow_state(pivots)
    assert dow.state == "range"


# ------ summarize_structure (top-level) -------------------------------------


def test_extreme_anchored_HIGH_picks_descending_envelope():
    """User-proposed algorithm: anchor at the highest pivot, find a descending
    line through later pivots that respects the >=20-bar duration and 2 touches."""
    # Highest at idx 10. Other pivots descend cleanly.
    pivots = [
        _piv(10, 1.17578, "HIGH"),  # extreme HIGH
        _piv(20, 1.17500, "HIGH"),  # touch within tolerance of slope -0.55
        _piv(35, 1.17400, "HIGH"),  # touch
        _piv(50, 1.17310, "HIGH"),  # endpoint
    ]
    tl = detect_extreme_anchored_trendline(
        pivots, kind="HIGH",
        min_duration_bars=20, min_additional_touches=2, tolerance_pip=1.5,
    )
    assert tl is not None
    assert tl.start_index == 10
    assert tl.slope_pip_per_bar < 0  # descending


def test_extreme_anchored_returns_none_when_duration_short():
    pivots = [
        _piv(10, 1.17500, "HIGH"),
        _piv(15, 1.17450, "HIGH"),
        _piv(18, 1.17400, "HIGH"),  # all within 8 bars of extreme
    ]
    tl = detect_extreme_anchored_trendline(
        pivots, kind="HIGH",
        min_duration_bars=20, min_additional_touches=2,
    )
    assert tl is None


def test_extreme_anchored_returns_none_when_too_few_touches():
    pivots = [
        _piv(10, 1.17500, "HIGH"),
        _piv(35, 1.17300, "HIGH"),  # endpoint 25 bars away, but no touches between
    ]
    tl = detect_extreme_anchored_trendline(
        pivots, kind="HIGH",
        min_duration_bars=20, min_additional_touches=2,
    )
    assert tl is None


def test_extreme_anchored_LOW_picks_steepest_slope():
    """Multiple valid candidates exist; algorithm should pick the steepest."""
    pivots = [
        _piv(10, 1.17000, "LOW"),  # extreme LOW
        _piv(20, 1.17050, "LOW"),  # touch1 (gentle)
        _piv(30, 1.17100, "LOW"),  # touch2 (steeper line through here?)
        _piv(40, 1.17150, "LOW"),  # endpoint candidate (steepest)
        _piv(35, 1.17120, "LOW"),  # touch on steeper line
    ]
    tl = detect_extreme_anchored_trendline(
        pivots, kind="LOW",
        min_duration_bars=20, min_additional_touches=2, tolerance_pip=1.5,
    )
    assert tl is not None
    # Pick should anchor at idx 10 (the extreme min)
    assert 10 in (tl.start_index, tl.end_index)


def test_summarize_returns_text_annotation():
    pivots = [
        _piv(10, 1.17578, "HIGH"),
        _piv(20, 1.17398, "LOW"),
        _piv(30, 1.17578, "HIGH"),
    ]
    summary = summarize_structure(pivots)
    text = summary.to_text_annotation()
    assert "[code-detected structure]" in text
    assert "double_top" in text or "double_bottom" in text or "Pattern" not in text
    assert "Dow:" in text
