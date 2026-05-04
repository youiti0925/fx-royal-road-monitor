---
description: Backfill outcomes for PENDING corpus entries whose 60-bar lookahead window has elapsed.
---

# /royal-road-update-outcomes

This command does not require any AI judgement. It walks the corpus,
identifies entries whose `outcome.status == "PENDING"`, fetches the
next 60 bars after each entry's `asof_utc`, computes the outcome
mechanically (WIN / LOSE / NEUTRAL_GOOD / NEUTRAL_MISSED), and
updates the entry.

Run:

```bash
python -m fx_monitor.tools.update_outcomes \
    --corpus-name default \
    --lookahead-bars 60
```

Report to the user: `examined`, `filled`, `skipped_too_recent`,
`failed`, and the new corpus size. If `failed > 0`, surface a hint
that yfinance may have rate-limited the fetch and the user can
retry later.
