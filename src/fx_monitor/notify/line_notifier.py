"""LINE Notify backend with optional ``imageFile`` attachment."""

from __future__ import annotations

import os
from pathlib import Path

from ..core.models import NotificationDecision

try:  # ``httpx`` is an optional runtime dependency (``[notify]`` extra).
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore[assignment]


class LineNotifier:
    name = "line"
    endpoint = "https://notify-api.line.me/api/notify"

    def __init__(self, token: str | None = None) -> None:
        self.token = token or os.environ.get("LINE_NOTIFY_TOKEN", "")

    def send(self, decision: NotificationDecision) -> bool:
        if not self.token:
            return False
        if httpx is None:
            return False

        message = f"[{decision.level}] {decision.title or decision.reason}"
        if decision.body:
            message += "\n" + decision.body
        headers = {"Authorization": f"Bearer {self.token}"}
        data = {"message": message[:1000]}

        image_path = decision.image_path
        try:
            if image_path and Path(image_path).exists():
                with Path(image_path).open("rb") as f:
                    resp = httpx.post(
                        self.endpoint,
                        headers=headers,
                        data=data,
                        files={"imageFile": ("royal_road_card.png", f, "image/png")},
                        timeout=20.0,
                    )
            else:
                resp = httpx.post(
                    self.endpoint,
                    headers=headers,
                    data=data,
                    timeout=10.0,
                )
            return resp.status_code < 300
        except Exception:
            return False


__all__ = ["LineNotifier"]
