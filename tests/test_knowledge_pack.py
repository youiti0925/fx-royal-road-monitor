from __future__ import annotations

from fx_monitor.knowledge.loader import DEFAULT_PATH, load_knowledge_pack


def test_default_pack_loads_and_is_substantial():
    pack = load_knowledge_pack(DEFAULT_PATH)
    assert len(pack) > 1000, "knowledge pack looks suspiciously small"
    assert "Royal Road" in pack.text
    # The five judgment categories must all be present.
    for verdict in ("PASS", "WAIT", "WARN", "BLOCK", "UNKNOWN"):
        assert verdict in pack.text


def test_pack_version_detected():
    pack = load_knowledge_pack(DEFAULT_PATH)
    assert "v1" in pack.version.lower()


def test_missing_pack_raises(tmp_path):
    import pytest

    bad = tmp_path / "nope.md"
    with pytest.raises(FileNotFoundError):
        load_knowledge_pack(bad)
