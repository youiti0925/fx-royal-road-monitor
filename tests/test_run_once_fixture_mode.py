from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _run(fixture_name: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["FX_MONITOR_FIXTURE_PATH"] = str(FIXTURES / fixture_name)
    env["AI_USE_MOCK"] = "true"
    env["DRY_RUN"] = "true"
    return subprocess.run(
        [sys.executable, "-m", "fx_monitor.app.run_once"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )


def test_run_once_with_ready_fixture():
    result = _run("royal_road_ready_sell_payload.json")
    assert "EURUSD=X" in result.stdout
    assert "READY" in result.stdout or "AGREE_PASS" in result.stdout


def test_run_once_with_wait_retest_fixture_not_ready():
    result = _run("royal_road_wait_retest_payload.json")
    # WAIT_RETEST should never end up as a READY notification.
    assert "[READY]" not in result.stdout


def test_run_once_with_event_block_fixture_not_ready():
    result = _run("royal_road_event_block_payload.json")
    assert "[READY]" not in result.stdout
