"""Per-entry post-mortem analysis.

Mechanical analysis only — no LLM call. Inputs:

- The CorpusEntry (judgement + market_pack + outcome)
- The actual future candles (so we can describe what happened)

Outputs a :class:`Postmortem` with:

- A failure-mode classification (why the outcome turned out as it did)
- Evidence: which line was hit, when, by how much
- Suspected procedure-step weak spots (the WAIT/UNKNOWN steps that, in
  hindsight, deserved a stronger answer)
- Concrete countermeasures the user can apply to the knowledge pack
  or the prompt
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from fx_monitor.corpus.outcome import _pip_size
from fx_monitor.corpus.schema import CorpusEntry
from fx_monitor.live.candle import Candle


FailureMode = Literal[
    "stop_hit",                 # price reversed past the AI-implied stop
    "target_overshot",          # price went well past the AI-implied target
    "did_not_move",             # price barely moved (wait was correct or moot)
    "moved_against_wait",       # AI was waiting; price ran the implied direction
    "moved_against_neutral",    # AI was NEUTRAL; market actually trended hard
    "outcome_pending",          # not enough future data
    "no_post_mortem_needed",    # WIN / NEUTRAL_GOOD with no actionable lesson
]


class StepSuspicion(BaseModel):
    step_key: str
    step_status: str
    note_ja: str


class Postmortem(BaseModel):
    schema_version: Literal["postmortem_v1"] = "postmortem_v1"
    entry_id: str
    failure_mode: FailureMode
    headline_ja: str
    facts_ja: list[str] = Field(default_factory=list)
    step_suspicions: list[StepSuspicion] = Field(default_factory=list)
    countermeasures_ja: list[str] = Field(default_factory=list)
    severity: Literal["low", "medium", "high"] = "low"


def _max_excursion(future: list[Candle], base: float) -> tuple[float, float, int, int]:
    """Return (max_high, min_low, idx_of_high, idx_of_low) in pip-distance terms.

    Distances are returned as price differences (not pip-converted) so the
    caller can render them however it wants.
    """
    if not future:
        return (base, base, 0, 0)
    best_high = future[0].h
    best_low = future[0].l
    high_idx = 0
    low_idx = 0
    for i, c in enumerate(future):
        if c.h > best_high:
            best_high = c.h
            high_idx = i
        if c.l < best_low:
            best_low = c.l
            low_idx = i
    return (best_high, best_low, high_idx, low_idx)


def _classify(entry: CorpusEntry, future: list[Candle]) -> FailureMode:
    if entry.outcome.status == "PENDING" or not future:
        return "outcome_pending"
    if entry.outcome.status in ("WIN", "NEUTRAL_GOOD"):
        return "no_post_mortem_needed"

    side = entry.judgement.side
    fav = entry.outcome.max_favorable_pip or 0.0
    adv = entry.outcome.max_adverse_pip or 0.0

    if entry.outcome.status == "LOSE":
        if side in ("BUY", "SELL"):
            return "stop_hit"
        # NEUTRAL but classified as LOSE means the SUPPRESSED/HOLD/EVENT_CLEAR
        # call was wrong because the market actually moved hard in either
        # direction.
        return "moved_against_neutral"

    if entry.outcome.status == "NEUTRAL_MISSED":
        # The judgement was a WAIT, and price ran the argued direction
        # without the AI giving an entry trigger.
        return "moved_against_wait"

    return "no_post_mortem_needed"


def _step_suspicions(entry: CorpusEntry, mode: FailureMode) -> list[StepSuspicion]:
    """Pick out steps that, given the failure mode, deserve scrutiny."""
    suspicions: list[StepSuspicion] = []
    steps = {s.key: s for s in entry.judgement.procedure_steps}

    def add(key: str, note: str) -> None:
        s = steps.get(key)
        if s is None:
            return
        suspicions.append(
            StepSuspicion(step_key=key, step_status=s.status, note_ja=note)
        )

    if mode == "stop_hit":
        # The directional setup invalidated. Likely the wave / dow read was
        # premature, or higher-TF context was missing.
        add("environment", "上位足の方向確認が不十分だった可能性 (UNKNOWN だった?)")
        add("htf_dow", "上位足ダウとの整合チェックが甘かった可能性")
        add("wave_pattern", "波形認定がフェイク(早すぎ)だった可能性")
        add("breakout", "ブレイク確定の閾値が緩く、ヒゲ抜けを真と扱った可能性")

    elif mode == "moved_against_wait":
        # AI was right about direction but kept waiting forever.
        add("breakout", "ブレイク確定基準が厳しすぎて待ちすぎた")
        add("retest", "リテスト要件を必須化した結果、初動を逃した")
        add("confirmation_candle", "確認足の閾値(ATR×?)が大きすぎた")
        add("entry_price", "ENTRYトリガーが具体化されておらず即応できなかった")

    elif mode == "moved_against_neutral":
        # NEUTRAL/HOLD/SUPPRESSED but market trended hard.
        add("environment", "環境認識が UNKNOWN のまま HOLD に倒したのが過剰防衛")
        add("wave_pattern", "形成中の波形を無視した可能性")
        add("horizontal_levels", "重要S/Rの突破を見逃した可能性")

    return suspicions


def _facts(entry: CorpusEntry, future: list[Candle]) -> list[str]:
    if not future:
        return ["未来データ未取得"]
    pip = _pip_size(entry.symbol)
    base = entry.market_pack.current_price
    bh, bl, hi, li = _max_excursion(future, base)
    bh_pip = (bh - base) / pip
    bl_pip = (bl - base) / pip
    last_close = future[-1].c
    last_pip = (last_close - base) / pip
    return [
        f"判定時点の価格: {base:.5f}",
        f"観察期間: 60本中 {len(future)}本 (経過時間≈{len(future)*5}分)",
        f"最高値到達: {bh:.5f} ({bh_pip:+.1f} pip) at +{hi+1}本目",
        f"最安値到達: {bl:.5f} ({bl_pip:+.1f} pip) at +{li+1}本目",
        f"観察期末close: {last_close:.5f} ({last_pip:+.1f} pip)",
    ]


def _countermeasures(mode: FailureMode, side: str) -> list[str]:
    if mode == "stop_hit":
        return [
            "上位足 (H1/H4) のピボットも数値事実 pack に追加し、上位足ダウとの整合を必須チェック化する",
            "波形認定に「最低 N 本の連続 LH/HL」を要求するよう知識 pack を厳格化",
            "ブレイク確定を「実体クローズ + 次足の方向継続」に変えてフェイクを除外",
            "RR 2.0 未達のシナリオは AI 出力時点で final_status を HOLD に強制降格",
        ]
    if mode == "moved_against_wait":
        return [
            "「波形が未確定だが上位足ダウと方向一致する場合は WAIT_TRIGGER を許可」を知識 pack に追記",
            "確認足の判定をリアルタイム化(現在の足が ATR×0.7 でも暫定的にカウントを許可)",
            "リテストを必須にせず、トレンド継続パターンも別 final_status で表現可能にする",
            "ENTRY価格を WAIT 段階でも具体的に提示するようプロンプトで強制",
        ]
    if mode == "moved_against_neutral":
        return [
            "HOLD/SUPPRESSED に倒す閾値を厳しくし、明確な根拠が無ければ UNKNOWN を選ぶ運用に変更",
            "上位足情報が無いことを理由に NEUTRAL に倒すのは禁止し、「データ不足のため判定保留」を別ステータスで分離",
            "重要S/R(複数タッチ)の突破イベントは即座に judgement を再評価",
        ]
    return []


def _severity(mode: FailureMode, fav_pip: float | None, adv_pip: float | None) -> str:
    if mode in ("no_post_mortem_needed", "outcome_pending"):
        return "low"
    magnitude = max(abs(fav_pip or 0.0), abs(adv_pip or 0.0))
    if magnitude >= 30:
        return "high"
    if magnitude >= 15:
        return "medium"
    return "low"


def _headline(mode: FailureMode, side: str) -> str:
    if mode == "stop_hit":
        return f"{side} 想定が逆方向に動いた (stop 想定価格を超えて反対側に到達)"
    if mode == "moved_against_wait":
        return f"{side} 待機中に想定方向へ走り抜けた (待ちが慎重すぎて初動を逃した)"
    if mode == "moved_against_neutral":
        return "NEUTRAL/HOLD と判断したが市場は実際に大きく動いた"
    if mode == "outcome_pending":
        return "outcome 未確定 (60本後の price action 待ち)"
    return "post-mortem 不要 (判定が結果と整合)"


def analyze(entry: CorpusEntry, future_candles: list[Candle]) -> Postmortem:
    mode = _classify(entry, future_candles)
    return Postmortem(
        entry_id=entry.entry_id,
        failure_mode=mode,
        headline_ja=_headline(mode, entry.judgement.side),
        facts_ja=_facts(entry, future_candles) if future_candles else [],
        step_suspicions=_step_suspicions(entry, mode),
        countermeasures_ja=_countermeasures(mode, entry.judgement.side),
        severity=_severity(  # type: ignore[arg-type]
            mode,
            entry.outcome.max_favorable_pip,
            entry.outcome.max_adverse_pip,
        ),
    )


__all__ = ["analyze", "Postmortem", "StepSuspicion", "FailureMode"]
