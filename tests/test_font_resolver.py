from __future__ import annotations

import pytest

from fx_monitor.render.font_resolver import (
    CJK_FONT_FAMILY_CANDIDATES,
    configure_matplotlib_japanese_font,
)


def test_configure_matplotlib_japanese_font_does_not_crash():
    selected = configure_matplotlib_japanese_font()
    assert selected is None or isinstance(selected, str)


def test_explicit_family_env_is_honored(monkeypatch):
    pytest.importorskip("matplotlib")
    monkeypatch.setenv("FX_MONITOR_FONT_FAMILY", "DejaVu Sans")
    monkeypatch.delenv("FX_MONITOR_CJK_FONT_PATH", raising=False)
    selected = configure_matplotlib_japanese_font()
    assert selected == "DejaVu Sans"


def test_candidates_list_is_nonempty_and_strings():
    assert CJK_FONT_FAMILY_CANDIDATES, "candidate list must not be empty"
    assert all(isinstance(x, str) and x for x in CJK_FONT_FAMILY_CANDIDATES)


def test_missing_font_path_falls_back_to_auto(monkeypatch):
    pytest.importorskip("matplotlib")
    monkeypatch.setenv("FX_MONITOR_CJK_FONT_PATH", "/no/such/font.otf")
    monkeypatch.delenv("FX_MONITOR_FONT_FAMILY", raising=False)
    # Must not raise even when the path is bogus.
    selected = configure_matplotlib_japanese_font()
    assert selected is None or isinstance(selected, str)
