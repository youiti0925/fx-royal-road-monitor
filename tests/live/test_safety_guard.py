from __future__ import annotations

import pytest

from fx_monitor.live.safety_guard import (
    FORBIDDEN_SUBSTRINGS,
    UnsafeEnvironmentError,
    _scan_loaded_modules,
    assert_safe_environment,
)


def test_forbidden_substrings_locked():
    """The forbidden list is part of the safety contract.

    Adding to the list is fine; silently shrinking it is not. Pin the
    minimum set so a regression must be conscious.
    """
    required = {
        "oanda",
        "paper_broker",
        "paper_trade",
        "live_order",
        "place_order",
        "broker_api",
        "execute_trade",
    }
    assert required.issubset(set(FORBIDDEN_SUBSTRINGS))


def test_assert_safe_environment_passes_in_clean_process():
    # The test process itself must not have any forbidden module loaded.
    assert_safe_environment()


@pytest.mark.parametrize(
    "fake_modname",
    [
        "oanda_client",
        "broker.paper_broker",
        "vendor.place_order_v2",
        "execute_trade_helper",
    ],
)
def test_scan_detects_substring_match(fake_modname: str):
    fake_loaded = {fake_modname: object()}
    hits = _scan_loaded_modules(fake_loaded)
    assert fake_modname in hits


def test_scan_ignores_unrelated_modules():
    fake_loaded = {
        "fx_monitor.live": object(),
        "fx_monitor.corpus": object(),
        "pandas": object(),
        "numpy": object(),
    }
    hits = _scan_loaded_modules(fake_loaded)
    assert hits == []


def test_assert_raises_when_forbidden_present(monkeypatch: pytest.MonkeyPatch):
    """Inject a forbidden module name into sys.modules and verify the guard fires."""
    import sys

    poisoned = dict(sys.modules)
    poisoned["oanda_v20_simulator"] = object()
    monkeypatch.setattr(sys, "modules", poisoned)

    with pytest.raises(UnsafeEnvironmentError) as excinfo:
        assert_safe_environment()
    assert "oanda_v20_simulator" in str(excinfo.value)


def test_live_package_imports_cleanly():
    """Importing fx_monitor.live in the test process must succeed.

    This proves the guard is not over-eager: legitimate test/runtime modules
    do not trip the substring filter.
    """
    import fx_monitor.live as live_pkg

    assert hasattr(live_pkg, "assert_safe_environment")
