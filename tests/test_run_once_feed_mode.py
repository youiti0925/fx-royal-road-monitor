from __future__ import annotations

import json
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


def test_run_once_csv_feed_draft_ai_review_mock_logs_but_never_ready(tmp_path):
    env = os.environ.copy()
    log_path = tmp_path / "review_log.jsonl"

    env.pop("FX_MONITOR_FIXTURE_PATH", None)
    env["FX_MONITOR_FEED"] = "csv"
    env["FX_MONITOR_CSV_PATH"] = str(FIXTURES / "ohlc_sample.csv")
    env["FX_MONITOR_SYMBOL"] = "EURUSD=X"
    env["FX_MONITOR_TIMEFRAME"] = "M5"
    env["AI_USE_MOCK"] = "true"
    env["DRY_RUN"] = "true"
    env["FX_MONITOR_REVIEW_DRAFT_WITH_AI"] = "true"
    env["FX_MONITOR_REVIEW_LOG_PATH"] = str(log_path)

    result = subprocess.run(
        [sys.executable, "-m", "fx_monitor.app.run_once"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Draft payload:" in result.stdout
    assert "OpenAI:" in result.stdout
    assert "Claude:" in result.stdout
    assert "Compare:" in result.stdout
    assert "Decision: SUPPRESSED" in result.stdout
    assert "Review log:" in result.stdout
    assert "[READY]" not in result.stdout

    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert lines, "review log is empty"
    data = json.loads(lines[0])
    assert data["mode"] == "draft_ai_review"
    assert data["decision"] == "SUPPRESSED"
    assert data["safety"]["ready_allowed"] is False
    assert data["safety"]["observation_only"] is True
    assert data["safety"]["used_in_final_action"] is False
    # Pin the log shape: no prompts / API keys / full payloads.
    forbidden = {"prompt", "system_prompt", "user_prompt", "api_key",
                 "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ai_payload",
                 "source_payload"}
    assert forbidden.isdisjoint(data.keys())


def test_run_once_csv_feed_draft_ai_review_real_disabled_logs_unknown(tmp_path):
    env = os.environ.copy()
    log_path = tmp_path / "review_log.jsonl"

    env.pop("FX_MONITOR_FIXTURE_PATH", None)
    env["FX_MONITOR_FEED"] = "csv"
    env["FX_MONITOR_CSV_PATH"] = str(FIXTURES / "ohlc_sample.csv")
    env["FX_MONITOR_SYMBOL"] = "EURUSD=X"
    env["FX_MONITOR_TIMEFRAME"] = "M5"
    env["AI_USE_MOCK"] = "false"
    env["OPENAI_ENABLED"] = "false"
    env["ANTHROPIC_ENABLED"] = "false"
    env["DRY_RUN"] = "true"
    env["FX_MONITOR_REVIEW_DRAFT_WITH_AI"] = "true"
    env["FX_MONITOR_REVIEW_LOG_PATH"] = str(log_path)

    result = subprocess.run(
        [sys.executable, "-m", "fx_monitor.app.run_once"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "OpenAI: UNKNOWN" in result.stdout
    assert "Claude: UNKNOWN" in result.stdout
    assert "Decision: SUPPRESSED" in result.stdout
    assert "[READY]" not in result.stdout

    assert log_path.exists()
    data = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert data["openai"]["verdict"] == "UNKNOWN"
    assert data["claude"]["verdict"] == "UNKNOWN"
    assert data["decision"] == "SUPPRESSED"


def test_run_once_csv_feed_writes_diagnostics(tmp_path):
    env = os.environ.copy()
    diag = tmp_path / "diagnostics.json"

    env.pop("FX_MONITOR_FIXTURE_PATH", None)
    env["FX_MONITOR_FEED"] = "csv"
    env["FX_MONITOR_CSV_PATH"] = str(FIXTURES / "ohlc_sample.csv")
    env["FX_MONITOR_SYMBOL"] = "EURUSD=X"
    env["FX_MONITOR_TIMEFRAME"] = "M5"
    env["AI_USE_MOCK"] = "false"
    env["OPENAI_ENABLED"] = "false"
    env["ANTHROPIC_ENABLED"] = "false"
    env["DRY_RUN"] = "true"
    env["FX_MONITOR_REVIEW_DRAFT_WITH_AI"] = "true"
    env["FX_MONITOR_DIAGNOSTICS_PATH"] = str(diag)

    result = subprocess.run(
        [sys.executable, "-m", "fx_monitor.app.run_once"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Diagnostics:" in result.stdout
    assert diag.exists()

    data = json.loads(diag.read_text(encoding="utf-8"))
    assert data["mode"] == "market_draft"
    assert data["feed"]["symbol"] == "EURUSD=X"
    assert data["draft"]["observation_only"] is True
    assert data["decision"]["level"] == "SUPPRESSED"
    assert data["safety"]["ready_allowed"] is False
    assert data["safety"]["dispatch_called"] is False
    # Pin: never store raw secrets.
    assert "OPENAI_API_KEY" not in json.dumps(data)
    assert "ANTHROPIC_API_KEY" not in json.dumps(data)


def test_run_once_csv_feed_diagnostics_emitted_when_review_off(tmp_path):
    env = os.environ.copy()
    diag = tmp_path / "diagnostics.json"

    env.pop("FX_MONITOR_FIXTURE_PATH", None)
    env["FX_MONITOR_FEED"] = "csv"
    env["FX_MONITOR_CSV_PATH"] = str(FIXTURES / "ohlc_sample.csv")
    env["FX_MONITOR_SYMBOL"] = "EURUSD=X"
    env["FX_MONITOR_TIMEFRAME"] = "M5"
    env["AI_USE_MOCK"] = "true"
    env["DRY_RUN"] = "true"
    # Review explicitly OFF.
    env["FX_MONITOR_REVIEW_DRAFT_WITH_AI"] = "false"
    env["FX_MONITOR_DIAGNOSTICS_PATH"] = str(diag)

    result = subprocess.run(
        [sys.executable, "-m", "fx_monitor.app.run_once"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Diagnostics:" in result.stdout
    assert diag.exists()
    data = json.loads(diag.read_text(encoding="utf-8"))
    assert data["ai"]["review_draft_with_ai"] is False
    assert data["ai"]["openai"]["verdict"] == "not_run"
    assert data["ai"]["claude"]["verdict"] == "not_run"
    assert data["decision"]["level"] == "SUPPRESSED"
