"""Discord webhook notifier with optional image attachment.

Sends ``decision.body`` as Discord message ``content``. If
``decision.image_path`` points to an existing file, posts the message and
the file together as a multipart upload (the same way Discord renders an
embedded image). All failure modes return ``False`` rather than raising.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..core.models import NotificationDecision

try:  # ``httpx`` is an optional runtime dependency (``[notify]`` extra).
    import httpx
except Exception:  # pragma: no cover - exercised when httpx is absent
    httpx = None  # type: ignore[assignment]


class DiscordNotifier:
    name = "discord"

    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", "")

    def send(self, decision: NotificationDecision) -> bool:
        if not self.webhook_url:
            return False
        if httpx is None:
            return False

        content = f"**[{decision.level}] {decision.title or decision.reason}**"
        if decision.body:
            content += f"\n```\n{decision.body}\n```"

        image_path = decision.image_path
        try:
            if image_path and Path(image_path).exists():
                with Path(image_path).open("rb") as f:
                    resp = httpx.post(
                        self.webhook_url,
                        data={
                            "payload_json": json.dumps(
                                {"content": content}, ensure_ascii=False
                            )
                        },
                        files={"file": ("royal_road_card.png", f, "image/png")},
                        timeout=20.0,
                    )
            else:
                resp = httpx.post(
                    self.webhook_url,
                    json={"content": content},
                    timeout=10.0,
                )
            return resp.status_code < 300
        except Exception:
            return False


__all__ = ["DiscordNotifier"]
