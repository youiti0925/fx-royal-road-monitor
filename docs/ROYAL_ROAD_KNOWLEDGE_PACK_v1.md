# Royal Road Knowledge Pack v1

## 0. Purpose

AI is not a signal generator.
AI is a royal-road procedure auditor.
AI must not rely on general market knowledge.
AI must judge only from provided payload and chart image.
If evidence is missing, use UNKNOWN or WAIT.

observation_only = true
used_in_final_action = false

## 1. Royal-road procedure order

The auditor must check these stages in order. Later stages may not be
considered PASS unless every prior required stage is PASS.

1. Environment
2. Higher timeframe direction
3. Dow structure
4. Support / resistance
5. Numeric trendline
6. Structural line
7. Wave pattern
8. Neckline
9. Breakout
10. Retest
11. Confirmation candle
12. Entry
13. Stop
14. Target
15. RR
16. Event
17. Final status

## 2. Status definitions

PASS:
  Clear evidence exists.

WAIT:
  Setup is valid but the next required stage has not happened.

WARN:
  Evidence exists but is weak, approximate, conflicting, or visually unclear.

BLOCK:
  Entry is forbidden.

UNKNOWN:
  Input is insufficient.

## 3. READY requirements for normal neckline_retest

READY is allowed only when all P0 conditions pass:

- wave pattern exists
- WNL exists
- WSL exists
- WTP exists
- structural neckline SNL exists or WNL clearly aligns with NL
- breakout confirmed
- retest confirmed
- confirmation_candle present
- entry_price exists
- stop_price exists
- target_price exists
- RR >= 2.0
- event risk is not BLOCK

confirmation_candle is P0.
Do not output READY without confirmation_candle.

READY is forbidden when any of the following is true:

- wave pattern missing
- WNL missing
- WSL missing or stop is not structural
- WTP missing or target is not structural
- breakout not confirmed (WAIT_BREAKOUT)
- retest not confirmed (WAIT_RETEST)
- confirmation_candle missing (WAIT_TRIGGER)
- RR < 2.0
- event is BLOCK (WAIT_EVENT_CLEAR)
- numeric trendline and structural trendline conflict on the main reason
- system says READY but chart evidence is weak (return WARN/WAIT instead)

## 4. WAIT status rules

WAIT_BREAKOUT:
  Pattern and WNL exist, but WNL has not broken.

WAIT_RETEST:
  WNL has broken, but retest is not confirmed.

WAIT_TRIGGER:
  Retest happened, but confirmation candle is missing.

WAIT_EVENT_CLEAR:
  Technical setup is READY-like, but event risk is BLOCK.

HOLD:
  Required evidence is missing, invalid, or contradictory.

## 5. Wave pattern rules

DT (double top, sell setup) requires:
- P1
- NL
- P2
- BR

DB (double bottom, buy setup) requires:
- B1
- NL
- B2
- BR

PASS:
  Parts exist and wave skeleton follows actual pivots.

WARN:
  Fallback pattern only.
  Wave points look weak or unclear.
  Skeleton does not visually follow pivots.

BLOCK:
  Pattern missing.
  Required parts missing.

The BREAK / RETEST / CONFIRM anchors are derived from these wave parts:

- BREAK anchor   = the candle that closes through NL / WNL.
- RETEST anchor  = the touch back near NL / WNL after BREAK.
- CONFIRM anchor = the confirmation_candle near WNL after RETEST.

These three anchors must reference real pivots / candles, not approximated
positions. If any anchor is approx, mark WARN.

## 6. W-line / structural line rules

WNL:
  wave neckline / entry trigger

WSL:
  wave structural invalidation / stop candidate

WTP:
  wave target candidate

SNL:
  structural neckline derived from NL / WNL

SIL:
  structural invalidation derived from WSL / P2 / B2

STP:
  structural target derived from WTP / BR / measured move

STL:
  structural trendline derived from P1-P2, B1-B2, HL-HL, or LH-LH

PASS:
  WNL/WSL/WTP exist and structural lines align.

WARN:
  W-lines exist but structural line is missing.
  Structural line anchor_quality is approx.
  Numeric and structural lines conflict.

BLOCK:
  WNL missing.
  Stop/target structural lines missing when required.

## 7. Numeric vs structural trendline

Numeric trendline:
  T1/T2/T3 detected from price statistics.

Structural trendline:
  STL from wave structure.

Do not treat them as the same.

PASS:
  Structural trendline is anchored to valid parts.
  Numeric line agrees or trendline is only supplemental.

WARN:
  Numeric line exists but structural line is weak.
  Structural and numeric line conflict.
  Anchor is approximate.
  Too many lines make the setup unclear.

BLOCK:
  Trendline is used as main reason but has no valid anchor.
  Trendline contradicts side.

## 8. Neckline

DT:
  Neckline relates to P1 -> NL -> P2 -> BR.

DB:
  Neckline relates to B1 -> NL -> B2 -> BR.

PASS:
  WNL and SNL exist and align with NL.

WARN:
  WNL exists but SNL missing.
  Neckline is unclear or repeatedly broken.

BLOCK:
  WNL missing.
  NL missing.

## 9. Breakout

SELL:
  close breaks below WNL.

BUY:
  close breaks above WNL.

PASS:
  breakout_confirmed true and marker anchored.

WAIT:
  WNL not broken.

WARN:
  breakout marker approx.
  wick-only or weak breakout.

BLOCK:
  breakout_quality BLOCK.
  WAIT_BREAKOUT shows confirmed BREAK/BR as if already happened.

## 10. Retest

PASS:
  retest_confirmed true and near WNL.

WAIT:
  breakout happened but retest not confirmed.

WARN:
  retest marker approx.
  retest too far from WNL.

BLOCK:
  neckline_retest READY without retest.

## 11. Confirmation candle

confirmation_candle is P0.

SELL:
  bearish rejection / bearish confirmation near WNL.

BUY:
  bullish rejection / bullish confirmation near WNL.

PASS:
  confirmation_candle exists and agrees with side.

WAIT:
  retest happened but confirmation missing.

WARN:
  candle weak or marker approx.

BLOCK:
  READY without confirmation candle.

## 12. Entry

PASS:
  READY has entry_price.
  entry is consistent with WNL / retest / confirmation.

WAIT:
  WAIT_BREAKOUT / WAIT_RETEST / WAIT_TRIGGER with no entry.

WARN:
  entry too early or too late.

BLOCK:
  READY without entry.
  WNL not broken but READY.
  retest missing but neckline_retest READY.

## 13. Stop

SELL:
  stop > entry.
  Prefer P2 high / WSL / SIL.

BUY:
  stop < entry.
  Prefer B2 low / WSL / SIL.

PASS:
  stop exists and is structural.

WARN:
  stop too far.
  stop too close.
  ATR-only without structure.

BLOCK:
  stop missing.
  invalid price order.
  stop inside structure.

## 14. Target

SELL:
  target < entry.

BUY:
  target > entry.

PASS:
  target exists and is WTP / STP / next SR / measured move.

WARN:
  target too far.
  obstacle before target.

BLOCK:
  target missing.
  invalid price order.

## 15. RR

Normal royal road:
  RR >= 2.0

PASS:
  rr >= 2.0 and stop/target are structurally valid.

WARN:
  rr passes but target/stop looks unrealistic.

BLOCK:
  rr < 2.0 or missing.

## 16. Event

PASS:
  event CLEAR.

WARN:
  event WARNING.

BLOCK:
  event BLOCK.

WAIT_EVENT_CLEAR:
  technical setup can remain visible, but no entry.

## 17. Final status rules

Do not output PASS unless all required P0 steps pass.

If system says READY but chart evidence is weak:
  return WARN or WAIT and add disagreement.

If evidence is missing:
  return UNKNOWN.

If event BLOCK:
  return BLOCK or WAIT_EVENT_CLEAR equivalent, never PASS.

## 18. Output contract

The reviewer must reply with a single JSON object that strictly matches the
JSON schema embedded in the prompt. The schema requires, among other fields:

- verdict in PASS/WAIT/WARN/BLOCK/UNKNOWN
- bias in long/short/none
- confidence in 0.0..1.0
- reasons (array)
- steps (array of per-stage status objects keyed by REQUIRED_STEP_KEYS)
- line_review, wave_review, entry_review, risk_review
- disagreement_with_system

If the reviewer cannot fill a required field honestly, the reviewer must
return verdict UNKNOWN. Hallucinated values are worse than UNKNOWN.
