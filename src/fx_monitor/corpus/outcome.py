"""Machine-derived outcome computation.

The point of computing outcomes from raw price action (instead of
asking the user) is that price is the ground truth, period. Whatever
the AI judged, the market either moved a certain way or didn't.

Conventions:

- Pip size is hard-coded per-symbol below. Add new symbols by extending
  :data:`PIP_SIZE_BY_SYMBOL`.
- ``max_favorable_pip`` is signed in the AI's intended direction.
  For a SELL judgement, downward movement is favourable.
- We observe at most ``max_bars`` future bars (default 60). Fewer bars
  yield a partial observation but still produce an outcome label.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fx_monitor.live.candle import Candle

from .schema import CorpusEntry, OutcomeLabel

PIP_SIZE_BY_SYMBOL: dict[str, float] = {
    "EURUSD=X": 0.0001,
    "GBPUSD=X": 0.0001,
    "USDJPY=X": 0.01,
    "AUDUSD=X": 0.0001,
    "USDCHF=X": 0.0001,
    "NZDUSD=X": 0.0001,
    "USDCAD=X": 0.0001,
}

DEFAULT_PIP_SIZE = 0.0001


def _pip_size(symbol: str) -> float:
    return PIP_SIZE_BY_SYMBOL.get(symbol, DEFAULT_PIP_SIZE)


def _signed_excursions(
    candles: list[Candle],
    *,
    base_price: float,
    pip: float,
    side: str,
) -> tuple[float, float, float]:
    """Return (max_favorable_pip, max_adverse_pip, close_diff_pip).

    Sign convention: favourable = direction the AI argued for.
    For SELL: downward = favourable. For BUY: upward = favourable.
    For NEUTRAL: we report |max excursion| as favourable and -|max| as
    adverse, treating either direction as "movement".
    """
    if not candles:
        return (0.0, 0.0, 0.0)
    highs_pip = [(c.h - base_price) / pip for c in candles]
    lows_pip = [(c.l - base_price) / pip for c in candles]
    last_close_pip = (candles[-1].c - base_price) / pip

    if side == "SELL":
        favourable = -min(lows_pip)  # bigger drop -> bigger favourable
        adverse = max(highs_pip)
        close_diff = -last_close_pip
    elif side == "BUY":
        favourable = max(highs_pip)
        adverse = -min(lows_pip)
        close_diff = last_close_pip
    else:
        upward = max(highs_pip)
        downward = -min(lows_pip)
        favourable = max(upward, downward)
        adverse = -favourable
        close_diff = abs(last_close_pip)
    return (favourable, adverse, close_diff)


def compute_outcome(
    entry: CorpusEntry,
    future_candles: list[Candle],
    *,
    max_bars: int = 60,
    ready_target_pip: float = 30.0,
    ready_stop_pip: float = 15.0,
    block_movement_pip: float = 30.0,
    wait_movement_pip: float = 15.0,
    now_utc: datetime | None = None,
) -> OutcomeLabel:
    """Derive an outcome label from price action after the judgement.

    The decision rules are deliberately simple and explicit so they are
    debuggable. The entry's ``judgement.final_status`` selects which
    rule applies.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    pip = _pip_size(entry.symbol)
    candles = future_candles[:max_bars]
    bars = len(candles)

    if bars == 0:
        return OutcomeLabel(status="PENDING", bars_observed=0)

    base_price = entry.market_pack.current_price
    side = entry.judgement.side
    favourable, adverse, close_diff = _signed_excursions(
        candles, base_price=base_price, pip=pip, side=side
    )

    final_status = entry.judgement.final_status

    # AiDecisionScreenSpec is observation-only by design — there is no
    # "READY" / "PASS" output. We score the WAIT_* family as directional
    # setups (the AI argued a side and expected the setup to develop),
    # and HOLD / SUPPRESSED / WAIT_EVENT_CLEAR as quiet-market calls.
    if final_status in ("WAIT_BREAKOUT", "WAIT_RETEST", "WAIT_TRIGGER"):
        if favourable >= ready_target_pip:
            status = "WIN"
        elif adverse >= ready_stop_pip:
            status = "LOSE"
        elif favourable >= wait_movement_pip:
            status = "NEUTRAL_MISSED"
        else:
            status = "NEUTRAL_GOOD"
    elif final_status in ("HOLD", "SUPPRESSED", "WAIT_EVENT_CLEAR"):
        if max(favourable, adverse) >= block_movement_pip:
            status = "LOSE"
        else:
            status = "WIN"
    else:
        # UNKNOWN or anything we did not recognise — do not score.
        status = "NEUTRAL_GOOD"

    return OutcomeLabel(
        status=status,  # type: ignore[arg-type]
        max_favorable_pip=favourable,
        max_adverse_pip=adverse,
        close_diff_pip=close_diff,
        bars_observed=bars,
        filled_at_utc=now_utc,
    )


__all__ = ["compute_outcome", "PIP_SIZE_BY_SYMBOL", "DEFAULT_PIP_SIZE"]
