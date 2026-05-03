from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_run_once_csv_feed_mode_builds_draft_but_not_ready():
    env = os.environ.copy()
    env.pop("FX_MONITOR_FIXTURE_PATH", None)
    env["FX_MONITOR_FEED"] = "csv"
    env["FX_MONITOR_CSV_PATH"] = str(FIXTURES / "ohlc_sample.csv")
    env["FX_MONITOR_SYMBOL"] = "EURUSD=X"
    env["FX_MONITOR_TIMEFRAME"] = "M5"
    env["AI_USE_MOCK"] = "true"
    env["DRY_RUN"] = "true"

    result = subprocess.run(
        [sys.executable, "-m", "fx_monitor.app.run_once"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Market snapshot:" in result.stdout
    assert "candles=5" in result.stdout
    assert "last_close=1.099" in result.stdout
    assert "Draft payload:" in result.stdout
    assert "observation_only=True" in result.stdout
    assert "Rule: UNKNOWN" in result.stdout
    assert "Decision: SUPPRESSED" in result.stdout
    assert "READY disabled" in result.stdout
    assert "[READY]" not in result.stdout


def test_run_once_csv_feed_missing_file_does_not_crash():
    env = os.environ.copy()
    env.pop("FX_MONITOR_FIXTURE_PATH", None)
    env["FX_MONITOR_FEED"] = "csv"
    env["FX_MONITOR_CSV_PATH"] = "/nonexistent/path.csv"
    env["FX_MONITOR_SYMBOL"] = "EURUSD=X"
    env["FX_MONITOR_TIMEFRAME"] = "M5"
    env["AI_USE_MOCK"] = "true"
    env["DRY_RUN"] = "true"

    result = subprocess.run(
        [sys.executable, "-m", "fx_monitor.app.run_once"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Market warnings:" in result.stdout
    assert "csv_not_found" in result.stdout
    # Draft mode still builds a (degenerate) draft and stays SUPPRESSED.
    assert "Draft payload:" in result.stdout
    assert "Decision: SUPPRESSED" in result.stdout
    assert "[READY]" not in result.stdout
