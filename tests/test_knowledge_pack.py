from __future__ import annotations

import pytest

from fx_monitor.knowledge.loader import DEFAULT_PATH, load_knowledge_pack


def test_default_pack_loads_and_is_substantial():
    pack = load_knowledge_pack(DEFAULT_PATH)
    assert len(pack) > 1000, "knowledge pack looks suspiciously small"
    assert "Royal Road" in pack.text
    for verdict in ("PASS", "WAIT", "WARN", "BLOCK", "UNKNOWN"):
        assert verdict in pack.text


def test_pack_version_detected():
    pack = load_knowledge_pack(DEFAULT_PATH)
    assert "v1" in pack.version.lower()


def test_pack_includes_w_lines_and_structural_lines():
    text = load_knowledge_pack(DEFAULT_PATH).text
    for token in ("WNL", "WSL", "WTP", "SNL", "SIL", "STP", "STL"):
        assert token in text, f"knowledge pack must define {token}"


def test_pack_includes_wave_parts_and_anchors():
    text = load_knowledge_pack(DEFAULT_PATH).text
    for token in ("P1", "P2", "B1", "B2", "NL", "BR"):
        assert token in text, f"knowledge pack must reference wave part {token}"
    for anchor in ("BREAK", "RETEST", "CONFIRM"):
        assert anchor in text, f"knowledge pack must reference anchor {anchor}"


def test_pack_includes_wait_states():
    text = load_knowledge_pack(DEFAULT_PATH).text
    for state in (
        "WAIT_BREAKOUT",
        "WAIT_RETEST",
        "WAIT_TRIGGER",
        "WAIT_EVENT_CLEAR",
    ):
        assert state in text, f"knowledge pack must define {state}"


def test_pack_includes_p0_and_rr_rules():
    text = load_knowledge_pack(DEFAULT_PATH).text
    assert "confirmation_candle is P0" in text
    assert "RR >= 2.0" in text


def test_pack_distinguishes_numeric_and_structural_trendline():
    text = load_knowledge_pack(DEFAULT_PATH).text
    assert "Numeric trendline" in text
    assert "Structural trendline" in text
    assert "Do not treat them as the same." in text


def test_pack_lists_ready_forbidden_conditions():
    text = load_knowledge_pack(DEFAULT_PATH).text
    assert "READY is forbidden when" in text
    for token in (
        "WAIT_BREAKOUT",
        "WAIT_RETEST",
        "WAIT_TRIGGER",
        "WAIT_EVENT_CLEAR",
    ):
        assert token in text


def test_missing_pack_raises(tmp_path):
    bad = tmp_path / "nope.md"
    with pytest.raises(FileNotFoundError):
        load_knowledge_pack(bad)
