---
description: Bootstrap or extend the past-judgement corpus from a historical OHLC archive.
---

# /build-corpus-from-history

Drives the offline batch runner. Each invocation processes a small
batch of historical candidates so a single Claude Code session does
not blow through subscription rate limits.

## Default arguments

- `--symbol EURUSD=X`
- `--timeframe M5`
- `--start <YYYY-MM-DD>` (e.g. 3 months back)
- `--end <YYYY-MM-DD>`
- `--ohlc-file <path>` JSONL/JSON archive of historical candles
  (use yfinance or any source to populate this once).
- `--batch-size 30`

## Workflow

For each candidate in the next batch (the runner picks them and
saves progress automatically):

1. The runner builds the prompt and writes it to a pending file
   (same shape as `/royal-road-check`).
2. Read the prompt file.
3. **Produce an AiDecisionScreenSpec JSON.** Use the knowledge pack,
   the few-shot examples in the pack, and any retrieved past
   entries shown in the prompt. Coordinates must be plausible.
4. Hand the spec back via `check_finalise` (or the equivalent
   batch helper).
5. Repeat until the batch is done, then **stop**. Tell the user
   `processed=N, remaining=M, run /build-corpus-from-history again
   later to continue`.

## Pacing rules (important)

- Do not exceed `batch_size` candidates per session.
- Do not loop into the next session automatically — the user
  invokes the slash command again when they have quota.
- If you hit a rate-limit or quota error, stop immediately. Progress
  is saved between candidates so resuming is safe.

## Forbidden

- Do not invent OHLC data. If the archive does not cover the
  requested range, ask the user to provide one.
- Do not call any external API for the judgement (this command
  must remain on the subscription path).
