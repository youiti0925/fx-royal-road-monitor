"""Discord webhook notifier (stub).

Real HTTP call is intentionally not made in the scaffold so unit tests can
import this module without network access. `httpx` is optional at runtime.
"""

from __future__ import annotations

import os

from ..core.models import NotificationDecision


class DiscordNotifier:
    name = "discord"

    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL", "")

    def send(self, decision: NotificationDecision) -> bool:
        if not self.webhook_url:
            return False
        try:
            import httpx
        except Exception:
            return False
        content = f"**[{decision.level}] {decision.title or decision.reason}**"
        if decision.body:
            content += f"\n```\n{decision.body}\n```"
        try:
            resp = httpx.post(self.webhook_url, json={"content": content}, timeout=10.0)
            return resp.status_code < 300
        except Exception:
            return False


__all__ = ["DiscordNotifier"]
