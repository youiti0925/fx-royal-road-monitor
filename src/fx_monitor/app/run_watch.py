"""Long-running 5-minute watcher.

Scaffold-level: simply loops `run_once.main()` every 5 minutes. CI uses
`monitor.yml` cron instead of running this directly.
"""

from __future__ import annotations

import sys
import time

from .run_once import main as run_once_main

INTERVAL_SECONDS = 300


def main(argv: list[str] | None = None) -> int:
    while True:
        rc = run_once_main(argv)
        if rc != 0:
            return rc
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
