"""Console notifier backend (always available, used in dry-run)."""

from __future__ import annotations

import sys

from ..core.models import NotificationDecision


class ConsoleNotifier:
    name = "console"

    def __init__(self, stream=sys.stdout) -> None:
        self.stream = stream

    def send(self, decision: NotificationDecision) -> bool:
        header = f"[{decision.level}] {decision.title or decision.reason}"
        print(header, file=self.stream)
        if decision.body:
            print(decision.body, file=self.stream)
        if decision.image_path:
            print(f"image: {decision.image_path}", file=self.stream)
        print("-" * 60, file=self.stream)
        return True


__all__ = ["ConsoleNotifier"]
