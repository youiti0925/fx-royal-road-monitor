from __future__ import annotations

from fx_monitor.core.models import NotificationDecision
from fx_monitor.notify import discord_notifier as mod
from fx_monitor.notify.discord_notifier import DiscordNotifier


class _DummyResp:
    def __init__(self, status: int = 204) -> None:
        self.status_code = status


def test_discord_notifier_sends_file_when_image_path_exists(monkeypatch, tmp_path):
    image = tmp_path / "card.png"
    image.write_bytes(b"png-data")

    calls: dict = {}

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls["kwargs"] = kwargs
        return _DummyResp(204)

    monkeypatch.setattr(mod.httpx, "post", fake_post)

    d = NotificationDecision(
        level="READY",
        reason="ready",
        title="READY EURUSD",
        body="body",
        image_path=str(image),
    )

    n = DiscordNotifier(webhook_url="https://discord.example/webhook")
    assert n.send(d) is True

    kwargs = calls["kwargs"]
    assert "files" in kwargs
    assert "file" in kwargs["files"]
    assert "payload_json" in kwargs["data"]


def test_discord_notifier_falls_back_to_text_when_no_image(monkeypatch):
    calls: dict = {}

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls["kwargs"] = kwargs
        return _DummyResp(204)

    monkeypatch.setattr(mod.httpx, "post", fake_post)

    d = NotificationDecision(level="READY", reason="ready", title="t", body="b")
    n = DiscordNotifier(webhook_url="https://discord.example/webhook")
    assert n.send(d) is True

    assert "files" not in calls["kwargs"]
    assert "json" in calls["kwargs"]


def test_discord_notifier_no_webhook_returns_false():
    d = NotificationDecision(level="READY", reason="ready")
    assert DiscordNotifier(webhook_url="").send(d) is False


def test_discord_notifier_post_failure_returns_false(monkeypatch):
    def fake_post(url, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(mod.httpx, "post", fake_post)
    d = NotificationDecision(level="READY", reason="ready")
    assert DiscordNotifier(webhook_url="https://x").send(d) is False
