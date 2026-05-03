from __future__ import annotations

from fx_monitor.core.models import NotificationDecision
from fx_monitor.notify import line_notifier as mod
from fx_monitor.notify.line_notifier import LineNotifier


class _DummyResp:
    def __init__(self, status: int = 200) -> None:
        self.status_code = status


def test_line_notifier_sends_image_file_when_image_path_exists(monkeypatch, tmp_path):
    image = tmp_path / "card.png"
    image.write_bytes(b"png-data")

    calls: dict = {}

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls["kwargs"] = kwargs
        return _DummyResp(200)

    monkeypatch.setattr(mod.httpx, "post", fake_post)

    d = NotificationDecision(
        level="READY",
        reason="ready",
        title="READY EURUSD",
        body="body",
        image_path=str(image),
    )

    n = LineNotifier(token="dummy-token")
    assert n.send(d) is True

    assert "files" in calls["kwargs"]
    assert "imageFile" in calls["kwargs"]["files"]


def test_line_notifier_falls_back_to_text_when_no_image(monkeypatch):
    calls: dict = {}

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls["kwargs"] = kwargs
        return _DummyResp(200)

    monkeypatch.setattr(mod.httpx, "post", fake_post)

    d = NotificationDecision(level="READY", reason="ready", title="t", body="b")
    assert LineNotifier(token="dummy-token").send(d) is True
    assert "files" not in calls["kwargs"]


def test_line_notifier_no_token_returns_false():
    d = NotificationDecision(level="READY", reason="ready")
    assert LineNotifier(token="").send(d) is False


def test_line_notifier_post_failure_returns_false(monkeypatch):
    def fake_post(url, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(mod.httpx, "post", fake_post)
    d = NotificationDecision(level="READY", reason="ready")
    assert LineNotifier(token="t").send(d) is False
