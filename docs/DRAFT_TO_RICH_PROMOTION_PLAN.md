# Draft to Rich Payload Promotion Plan

This document defines how an observation-only OHLC draft payload may
eventually become a rich royal-road payload.

This document does not enable READY.
This document does not enable notifications.
This document does not enable trading.

## 0. Current safety state

Current feed mode:

```
OHLC
→ MarketSnapshot
→ RoyalRoadDraftPayload
→ MonitorCase(draft)
→ evaluate_monitor_case = UNKNOWN or WARN
→ optional AI draft review
→ review log / diagnostics / dashboard
→ Decision SUPPRESSED
```

Current hard contract:

```
observation_only = true
used_in_final_action = false
entry_plan.entry_status = HOLD
royal_road_procedure_checklist.p0_pass = false
draft mode decision = SUPPRESSED
draft mode dispatch = not called
draft mode READY = impossible
```

This contract must not be weakened.

## 1. Why promotion needs phases

Raw OHLC is not enough to produce a safe READY signal.

A READY signal requires a full royal-road structure:

```
environment
→ Dow structure
→ support / resistance
→ trendline
→ structural lines
→ wave pattern
→ WNL / WSL / WTP
→ breakout
→ retest
→ confirmation candle
→ ENTRY
→ STOP
→ TP
→ RR
→ event clear
```

Therefore promotion must be staged.

No phase may skip directly from rough OHLC pivots to READY.

## 2. Phase P0: Observation-only draft

Status:

```
implemented
```

Input:

```
MarketSnapshot
```

Output:

```
RoyalRoadDraftPayload
```

Allowed:

```
pivots
rough_support_resistance
rough_wave_context
warnings
AI draft review logs
offline dashboard
```

Forbidden:

```
entry_plan READY
p0_pass true
notification dispatch
READY notification
trading
```

Required verdict:

```
evaluate_monitor_case = UNKNOWN or WARN
Decision = SUPPRESSED
```

## 3. Phase P1: Rich structure draft

Status:

```
first implementation added
```

Purpose:

Create rich royal-road-like payload keys from OHLC, still
observation-only.

Input:

```
MarketSnapshot
PivotPoint[]
rough_support_resistance
rough_wave_context
```

Output keys:

```
pattern_levels_draft
wave_derived_lines_draft
structural_lines_draft
support_resistance_v2_draft
trendline_context_draft
royal_road_procedure_checklist_draft
```

Important:

```
These keys are drafts.
They must not be treated as production evidence.
```

Allowed status:

```
HOLD
WAIT_BREAKOUT
WAIT_RETEST
WAIT_TRIGGER
UNKNOWN
WARN
```

Forbidden:

```
READY
p0_pass true
used_in_final_action true
dispatch
```

Minimum tests:

```
draft rich keys exist
entry_status is not READY
p0_pass is false
evaluate_monitor_case never PASS
```

## 4. Phase P2: Visual validation

Purpose:

Render the draft structural lines so a human can inspect them.

Output:

```
draft dashboard chart
P1/NL/P2/BR or B1/NL/B2/BR
draft WNL/WSL/WTP
draft SNL/SIL/STP/STL
rough S/R zones
```

Allowed:

```
offline dashboard
artifact image
manual review
```

Forbidden:

```
READY
notification dispatch
```

Required:

```
Every line must include source and confidence:
  source = draft
  confidence = numeric value
  anchor_parts
  warnings
```

## 5. Phase P3: Backtest-only candidate evaluation

Status:

```
scaffold added
```

Purpose:

Evaluate whether draft-derived structures match past known rich
payloads.

Input:

```
historical OHLC
known rich royal-road fixtures
existing youiti0925/test preview payloads, if exported safely
```

Output:

```
matching report
false positive report
false negative report
```

Allowed:

```
offline backtest
comparison report
precision / recall style metrics
```

Forbidden:

```
live notification
READY production notification
trading
```

Promotion requirement:

```
must show acceptable false positive rate
must show no systematic unsafe READY
must be reviewed manually
```

## 6. Phase P4: WAIT-only production monitor

Purpose:

Allow real feed mode to generate WAIT/HOLD rich payloads in
production.

Allowed statuses:

```
WAIT_BREAKOUT
WAIT_RETEST
WAIT_TRIGGER
WAIT_EVENT_CLEAR
HOLD
UNKNOWN
WARN
```

Forbidden:

```
READY
AGREE_PASS notification
entry notification
```

Decision:

```
SUPPRESSED or INFO only
```

Required gates:

```
event BLOCK cannot be bypassed
p0_pass must remain false
used_in_final_action must remain false
```

## 7. Phase P5: READY-eligible shadow mode

Purpose:

Allow the system to calculate what would have been READY, but not
notify.

Output:

```
shadow_ready_candidate
shadow_decision
shadow_notification = false
```

Allowed:

```
shadow READY in logs
shadow dashboard
manual review
```

Forbidden:

```
actual READY notification
Discord / LINE dispatch
trading
```

Required:

```
OpenAI PASS
Claude PASS
rule PASS
bias match
calendar clear
cooldown clear
manual review over multiple runs
```

## 8. Phase P6: READY notification approval gate

READY notification from real feed mode is allowed only after
explicit approval.

Required conditions:

```
dashboard SAFE across multiple scheduled runs
feed stable
AI UNKNOWN reasons understood
missing/disagreement reports reviewed
draft-to-rich false positives reviewed
shadow READY reviewed
notification content reviewed
manual approval recorded in docs
```

Even then:

```
no auto trading
no order execution
no broker connection
notification only
```

## 9. Never allowed without a separate explicit project

The following are out of scope:

```
OANDA live trading
paper broker
auto trading
place order
position management
broker API key storage
```

These require a separate safety review and a separate explicit
instruction.

## 10. Required implementation order

The only allowed order is:

```
P0 observation-only draft
P1 rich structure draft
P2 visual validation
P3 backtest-only candidate evaluation
P4 WAIT-only production monitor
P5 READY-eligible shadow mode
P6 READY notification approval gate
```

Do not skip phases.

## 11. Terms

Draft:

```
observation-only
not used in final action
not READY eligible
```

Rich draft:

```
has royal-road keys
still observation-only
not READY eligible
```

Shadow READY:

```
would-have-been READY
logged only
not dispatched
```

READY notification:

```
actual user-facing alert
requires explicit approval
```

Trading:

```
out of scope
never enabled by this plan
```
