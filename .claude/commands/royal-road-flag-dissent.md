---
description: Mark a corpus entry as user-dissent so future retrieval can use it as a negative example.
---

# /royal-road-flag-dissent

The user is telling the system "this judgement was off" or "I would
have called this differently". Persist that as a flag on the entry —
no other state change.

Required: `--id <entry_id>`. Optional: `--note "<short reason>"`.

Run:

```bash
python -m fx_monitor.tools.flag_dissent \
    --id <entry_id> \
    --note "<note>"
```

Report success / failure and the entry's id.
