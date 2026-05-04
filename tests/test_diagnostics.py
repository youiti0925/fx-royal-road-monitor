from __future__ import annotations

import json

from fx_monitor.logging.diagnostics import write_diagnostics


def test_write_diagnostics_writes_json_and_redacts_secrets(tmp_path):
    path = tmp_path / "diagnostics.json"
    write_diagnostics(
        path=path,
        data={
            "mode": "test",
            "OPENAI_API_KEY": "secret-key",
            "nested": {
                "token": "secret-token",
                "safe": "ok",
            },
        },
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["diagnostics_schema"] == "fx_monitor_diagnostics_v1"
    assert data["OPENAI_API_KEY"] == "***redacted***"
    assert data["nested"]["token"] == "***redacted***"
    assert data["nested"]["safe"] == "ok"
    assert "written_at_utc" in data


def test_write_diagnostics_redacts_webhook_keys(tmp_path):
    path = tmp_path / "d.json"
    write_diagnostics(
        path=path,
        data={
            "DISCORD_WEBHOOK_URL": "https://example/1",
            "LINE_NOTIFY_TOKEN": "abc",
            "channel": {"webhook": "https://x"},
        },
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["DISCORD_WEBHOOK_URL"] == "***redacted***"
    assert data["LINE_NOTIFY_TOKEN"] == "***redacted***"
    assert data["channel"]["webhook"] == "***redacted***"


def test_write_diagnostics_handles_lists_and_datetimes(tmp_path):
    from datetime import datetime, timezone

    path = tmp_path / "d.json"
    write_diagnostics(
        path=path,
        data={
            "items": [{"api_key": "kkk", "ok": 1}, "plain"],
            "now": datetime(2026, 5, 4, 1, 2, 3, tzinfo=timezone.utc),
        },
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["items"][0]["api_key"] == "***redacted***"
    assert data["items"][0]["ok"] == 1
    assert data["items"][1] == "plain"
    assert data["now"].startswith("2026-05-04")


def test_write_diagnostics_creates_parent_dirs(tmp_path):
    path = tmp_path / "deep" / "nest" / "d.json"
    write_diagnostics(path=path, data={"mode": "x"})
    assert path.exists()
