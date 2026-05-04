---
description: Run a single royal-road decision check on the most recent OHLC and store the AI judgement in the corpus.
---

# /royal-road-check

You are the AI judge for the v2 royal-road observation pipeline.
The system is observation-only — your judgement never triggers
notifications or trades. Hard-locked safety flags:
`observation_only=true / used_for_*=false`.

## Workflow

1. Decide the OHLC source. The user can pass `--ohlc-file <path>`
   (a JSON or JSONL of candle records). If they don't, fetch the
   latest OHLC manually (yfinance or any source they prefer) and
   write it to `data/ohlc/latest.json`.

2. Run:

   ```bash
   python -m fx_monitor.tools.check_prepare \
       --ohlc-file <path> \
       --symbol EURUSD=X \
       --timeframe M5
   ```

   This prints JSON containing `entry_id`, `prompt_path`, and
   `pending_path`.

3. Read the file at `prompt_path`. Follow the SYSTEM and USER
   prompts inside. **Produce a single AiDecisionScreenSpec JSON**
   matching `src/fx_monitor/ai/decision_screen_spec_schema.py`.
   Keep the four safety flags as they are.

4. Run:

   ```bash
   python -m fx_monitor.tools.check_finalise \
       --id <entry_id> \
       --json '<the spec json>'
   ```

   This validates, downgrades to `UNKNOWN` if Layer 3 finds errors,
   and stores the entry in the corpus.

5. Report to the user: `final_status`, `side`, validation result,
   corpus size, and any warnings worth flagging.

## Output expectations

- Be concise. The user sees your message and decides whether to
  trade. Put the headline on the first line.
- Never claim READY or "trigger now" — the system forbids it.
- If the validation flagged warnings, surface them so the user
  knows the AI may have hallucinated coordinates.
