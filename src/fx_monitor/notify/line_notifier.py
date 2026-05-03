"""LINE Notify backend (stub)."""

from __future__ import annotations

import os

from ..core.models import NotificationDecision


class LineNotifier:
    name = "line"
    endpoint = "https://notify-api.line.me/api/notify"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("LINE_NOTIFY_TOKEN", "")

    def send(self, decision: NotificationDecision) -> bool:
        if not self.token:
            return False
        try:
            import httpx
        except Exception:
            return False
        message = f"[{decision.level}] {decision.title or decision.reason}"
        if decision.body:
            message += "\n" + decision.body
        try:
            resp = httpx.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self.token}"},
                data={"message": message[:1000]},
                timeout=10.0,
            )
            return resp.status_code < 300
        except Exception:
            return False


__all__ = ["LineNotifier"]
