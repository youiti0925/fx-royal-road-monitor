---
description: Regenerate the static HTML dashboard from the current corpus.
---

# /royal-road-dashboard

Run:

```bash
python -m fx_monitor.tools.dashboard \
    --corpus-name default \
    --days 30
```

This rewrites `docs/live_dashboard/index.html` and per-entry pages
under `docs/live_dashboard/entries/`. No external services are
involved; the user opens the HTML directly via `file://`.

Report to the user:

- The output root path.
- How many entries are in the corpus and how many entry pages were
  written for the recent window.
- A reminder to run `/royal-road-update-outcomes` first if many
  entries are still PENDING.
