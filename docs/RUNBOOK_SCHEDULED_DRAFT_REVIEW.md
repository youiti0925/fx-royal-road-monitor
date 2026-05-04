# Scheduled Draft Review Runbook

This runbook explains how to inspect the scheduled draft review workflow.

This workflow is observation-only — not used for READY decisions,
not used for notification dispatch, not used for trading, and not used
for order execution.

It is not used for:

- READY decisions
- notifications
- trading
- order execution

## 1. What this workflow does

On schedule or manual dispatch, the workflow:

1. runs tests
2. loads market data
3. builds an observation-only draft payload
4. optionally asks OpenAI / Claude to review the draft
5. writes `out/review_log.jsonl`
6. writes `out/review_report.md`
7. writes `out/review_report.json`
8. writes `out/diagnostics.json`
9. writes `out/dashboard.html`
10. uploads these files as a GitHub Actions artifact

## 2. Where to check

Open:

1. GitHub repository
2. Actions
3. Latest `monitor` workflow run
4. Job: `draft-review`
5. Artifacts
6. Download `draft-review-<run_id>`

Inside the artifact, open:

```
dashboard.html
```

This is the first file to check.

## 3. Normal result

A normal scheduled draft review has:

```
dashboard.html:
  safety banner = SAFE: offline analysis only
  decision.level = SUPPRESSED
  safety.ready_allowed = false
  safety.dispatch_called = false

diagnostics.json:
  mode = market_draft
  decision.level = SUPPRESSED
  safety.ready_allowed = false
  safety.dispatch_called = false

review_report.json:
  safety.used_for_ready = false
  safety.used_for_notification = false
  safety.offline_analysis_only = true
```

`[READY]` should not appear in the draft-review job. **No [READY]** is
the load-bearing invariant of this workflow — if you ever see it, treat
it as an incident.

## 4. If Yahoo/yfinance returns no data

This is not a trading error.

Check:

```
diagnostics.json:
  feed.candles
  feed.warnings
```

Possible warnings:

```
yfinance_import_failed
yahoo_download_failed
yahoo_empty_dataframe
yahoo_parse_failed
```

Expected behavior:

```
Decision remains SUPPRESSED
No notification is sent
Artifacts are still uploaded
```

## 5. If OpenAI / Claude are UNKNOWN

This is allowed.

Check:

```
diagnostics.json:
  ai.openai.verdict
  ai.openai.reasons
  ai.claude.verdict
  ai.claude.reasons
  ai.compare.result
```

Common reasons:

```
openai_disabled
anthropic_disabled
openai_api_key_missing
anthropic_api_key_missing
openai_review_failed
anthropic_review_failed
```

Expected behavior:

```
compare.result = INSUFFICIENT
decision.level = SUPPRESSED
No notification is sent
```

## 6. If dashboard says CHECK SAFETY FLAGS

Treat this as a serious safety signal.

Check:

```
diagnostics.json:
  decision.level
  safety.ready_allowed
  safety.dispatch_called

review_report.json:
  safety.used_for_ready
  safety.used_for_notification
```

Expected safe values:

```
decision.level = SUPPRESSED
safety.ready_allowed = false
safety.dispatch_called = false
safety.used_for_ready = false
safety.used_for_notification = false
```

If any value differs, do not enable notifications. Open an issue,
revert the offending change, and re-run the workflow before doing
anything else.

## 7. Files in the artifact

```
review_log.jsonl:
  raw append-only summary records for each draft AI review

review_report.md:
  human-readable aggregate summary

review_report.json:
  structured aggregate summary

diagnostics.json:
  per-run feed / draft / AI / decision / safety diagnostics

dashboard.html:
  first file to open; combines diagnostics and summary into one page
```

## 8. Safety contract

The scheduled draft-review workflow must always satisfy:

```
DRY_RUN = true
FX_MONITOR_RENDER_CARD = false
FX_MONITOR_ATTACH_CARD = false
draft mode decision = SUPPRESSED
draft mode dispatch = not called
draft mode READY = impossible
```

Forbidden:

```
broker connection
live trading
paper trading
order execution
READY notification from draft mode
Discord / LINE dispatch from draft mode
API keys committed to repo
```

These items are pinned by `tests/test_workflow_static.py` and
`tests/test_runbook_static.py`. A change that breaks any of them will
fail CI before it can ship.

## 9. Manual local smoke

Run:

```bash
mkdir -p out

DRY_RUN=true \
AI_USE_MOCK=false \
OPENAI_ENABLED=false \
ANTHROPIC_ENABLED=false \
FX_MONITOR_FEED=csv \
FX_MONITOR_CSV_PATH=tests/fixtures/ohlc_sample.csv \
FX_MONITOR_SYMBOL=EURUSD=X \
FX_MONITOR_TIMEFRAME=M5 \
FX_MONITOR_REVIEW_DRAFT_WITH_AI=true \
FX_MONITOR_REVIEW_LOG_PATH=out/review_log.jsonl \
FX_MONITOR_DIAGNOSTICS_PATH=out/diagnostics.json \
python -m fx_monitor.app.run_once

python -m fx_monitor.app.review_report \
  --log out/review_log.jsonl \
  --md out/review_report.md \
  --json out/review_report.json

python -m fx_monitor.app.dashboard \
  --diagnostics out/diagnostics.json \
  --summary out/review_report.json \
  --html out/dashboard.html
```

Expected:

```
Decision: SUPPRESSED
Review log: out/review_log.jsonl
Diagnostics: out/diagnostics.json
Dashboard: out/dashboard.html
No [READY]
```

## 10. Do not proceed to real notifications until

Do not enable Discord / LINE production notifications until:

1. dashboard stays SAFE across multiple runs
2. feed data is stable
3. AI UNKNOWN reasons are understood
4. missing / disagreement reports are reviewed
5. draft-to-rich-payload promotion plan is explicitly approved
