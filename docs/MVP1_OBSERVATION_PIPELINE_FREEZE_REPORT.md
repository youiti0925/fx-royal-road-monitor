# MVP-1 Observation Pipeline Freeze Report

## Status

MVP-1 is observation-only.

It does not produce READY.
It does not dispatch notifications.
It does not trade.

## Implemented

- CSV / Yahoo market feed
- MarketSnapshot
- RoyalRoadDraftPayload
- rich_draft keys
  - pattern_levels_draft
  - wave_derived_lines_draft
  - structural_lines_draft
  - support_resistance_v2_draft
  - trendline_context_draft
  - royal_road_procedure_checklist_draft
- draft chart image (`out/draft_chart.png`)
- OpenAI / Claude draft review logs (`out/review_log.jsonl`)
- diagnostics.json (`out/diagnostics.json`)
- review_report.md (`out/review_report.md`)
- review_report.json (`out/review_report.json`)
- dashboard.html (`out/dashboard.html`)
- offline rich draft compare scaffold (`out/rich_draft_compare.json`)
- scheduled GitHub Actions workflow that uploads the above as
  `draft-review-<run_id>` artifacts on a 5-minute cron and on manual
  dispatch (push / pull-request runs only execute pytest)

## Safety contract

```
observation_only = true
used_in_final_action = false
entry_plan.entry_status = HOLD
p0_pass = false
ready_eligible = false
decision = SUPPRESSED
dispatch = not called
READY = impossible from feed mode
```

These invariants are pinned by tests:

- `tests/test_rule_engine_royal_road_payload.py`
- `tests/test_draft_payload.py`
- `tests/test_rich_draft.py`
- `tests/test_rich_draft_compare.py`
- `tests/test_run_once_feed_mode.py`
- `tests/test_dashboard.py`
- `tests/test_workflow_static.py`
- `tests/test_runbook_static.py`
- `tests/test_promotion_plan_static.py`

## What to inspect first

Open:

```
out/dashboard.html
```

Then check, in this order:

```
out/draft_chart.png
out/diagnostics.json
out/review_report.md
out/rich_draft_compare.json
```

The dashboard shows a green "SAFE: offline analysis only" banner when
every safety flag is correct; if it ever flips to red ("CHECK SAFETY
FLAGS"), stop and read `out/diagnostics.json` and the runbook.

## Stop condition

Do not proceed to P4 until a human has reviewed:

- dashboard safety banner (must stay green across multiple runs)
- draft chart line quality (P1 / NL / P2 / BR or B1 / NL / B2 / BR
  positions look right)
- AI missing reasons (top items in `review_report.md`)
- AI disagreement reasons (top items in `review_report.md`)
- rich draft compare scores (`out/rich_draft_compare.json`)
- whether the draft lines are humanly acceptable

## Next possible phases

Per `docs/DRAFT_TO_RICH_PROMOTION_PLAN.md`:

- P4 WAIT-only production monitor — **not approved yet**
- P5 shadow READY                  — **not approved yet**
- P6 READY notification            — **not approved yet**
- Trading                          — **out of scope** (separate
  project + separate safety review required)

## Related documents

- `docs/RUNBOOK_SCHEDULED_DRAFT_REVIEW.md`
- `docs/DRAFT_TO_RICH_PROMOTION_PLAN.md`
- `docs/AI_REVIEW_POLICY.md`
- `docs/NOTIFICATION_POLICY.md`
- `docs/ROYAL_ROAD_KNOWLEDGE_PACK_v1.md`
