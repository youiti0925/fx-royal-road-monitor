from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _run(fixture_name: str, **overrides: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["FX_MONITOR_FIXTURE_PATH"] = str(FIXTURES / fixture_name)
    env["AI_USE_MOCK"] = "true"
    env["DRY_RUN"] = "true"
    env.update(overrides)
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


def test_run_once_ready_fixture_generates_notification_card(tmp_path):
    pytest_importorskip = __import__("pytest").importorskip
    pytest_importorskip("matplotlib")

    env = os.environ.copy()
    card = tmp_path / "notification_card.png"
    env["FX_MONITOR_FIXTURE_PATH"] = str(FIXTURES / "royal_road_ready_sell_payload.json")
    env["AI_USE_MOCK"] = "true"
    env["DRY_RUN"] = "true"
    env["FX_MONITOR_RENDER_CARD"] = "true"
    env["FX_MONITOR_CARD_PATH"] = str(card)

    result = subprocess.run(
        [sys.executable, "-m", "fx_monitor.app.run_once"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Notification card:" in result.stdout
    assert card.exists()
    assert card.stat().st_size > 5000


def test_run_once_ready_fixture_generates_and_attaches_card_path(tmp_path):
    pytest_importorskip = __import__("pytest").importorskip
    pytest_importorskip("matplotlib")

    env = os.environ.copy()
    card = tmp_path / "notification_card.png"
    env["FX_MONITOR_FIXTURE_PATH"] = str(FIXTURES / "royal_road_ready_sell_payload.json")
    env["AI_USE_MOCK"] = "true"
    env["DRY_RUN"] = "true"
    env["FX_MONITOR_RENDER_CARD"] = "true"
    env["FX_MONITOR_CARD_PATH"] = str(card)
    env["FX_MONITOR_ATTACH_CARD"] = "true"

    result = subprocess.run(
        [sys.executable, "-m", "fx_monitor.app.run_once"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Notification card:" in result.stdout
    assert "Attach card: yes" in result.stdout
    assert "image:" in result.stdout
    assert card.exists()
    assert card.stat().st_size > 5000


def test_run_once_attach_card_disabled_does_not_set_image_path(tmp_path):
    pytest_importorskip = __import__("pytest").importorskip
    pytest_importorskip("matplotlib")

    env = os.environ.copy()
    card = tmp_path / "card.png"
    env["FX_MONITOR_FIXTURE_PATH"] = str(FIXTURES / "royal_road_ready_sell_payload.json")
    env["AI_USE_MOCK"] = "true"
    env["DRY_RUN"] = "true"
    env["FX_MONITOR_RENDER_CARD"] = "true"
    env["FX_MONITOR_CARD_PATH"] = str(card)
    env["FX_MONITOR_ATTACH_CARD"] = "false"

    result = subprocess.run(
        [sys.executable, "-m", "fx_monitor.app.run_once"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Attach card: no" in result.stdout
    # ConsoleNotifier prints `image: ...` only when decision.image_path is set;
    # with attachment disabled we should not see it.
    assert "image:" not in result.stdout


def test_run_once_real_reviewers_disabled_suppresses_ready_fixture():
    result = _run(
        "royal_road_ready_sell_payload.json",
        AI_USE_MOCK="false",
        OPENAI_ENABLED="false",
        ANTHROPIC_ENABLED="false",
    )
    # With both real reviewers disabled, both come back UNKNOWN -> compare
    # is INSUFFICIENT and the notifier suppresses any notification.
    assert "INSUFFICIENT" in result.stdout
    assert "Decision: SUPPRESSED" in result.stdout
    assert "[READY]" not in result.stdout
    assert "[WATCH]" not in result.stdout


def test_run_once_real_reviewers_missing_keys_suppresses_ready_fixture():
    env_overrides = dict(
        AI_USE_MOCK="false",
        OPENAI_ENABLED="true",
        ANTHROPIC_ENABLED="true",
    )
    # Make sure no key leaks in from the test environment.
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env.pop("ANTHROPIC_API_KEY", None)
    env["FX_MONITOR_FIXTURE_PATH"] = str(FIXTURES / "royal_road_ready_sell_payload.json")
    env["DRY_RUN"] = "true"
    env.update(env_overrides)

    result = subprocess.run(
        [sys.executable, "-m", "fx_monitor.app.run_once"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "openai_api_key_missing" in result.stdout
    assert "anthropic_api_key_missing" in result.stdout
    assert "Decision: SUPPRESSED" in result.stdout
    assert "[READY]" not in result.stdout
    assert "[WATCH]" not in result.stdout
