---
description: Generate a monthly self-diagnosis report from the corpus.
---

# /royal-road-monthly-report

Run:

```bash
python -m fx_monitor.tools.monthly_report \
    --corpus-name default \
    --days 30
```

The output JSON contains: per-final_status counts, side counts,
outcome distribution, win rate among scored entries, dissent count,
total entries in window, and total corpus size.

When reporting back to the user:

- Lead with the headline win rate (or "no scored entries yet").
- Highlight any dissent count > 0.
- If `outcome_counts.PENDING` is high, suggest running
  `/royal-road-update-outcomes` first.
