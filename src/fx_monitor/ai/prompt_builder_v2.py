"""Prompt builder for the v2 AI judge.

The v2 prompt deliberately contains only numeric facts plus retrieved
past similar cases. No code-derived pattern names, neckline guesses,
or trendline parameters reach the AI — those would be the AI's own job
to decide.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fx_monitor.ai.decision_screen_spec_schema import AiDecisionScreenSpec
from fx_monitor.live.market_pack_v2 import MarketAnalysisPackV2

DEFAULT_KNOWLEDGE_PACK_PATH = (
    Path(__file__).parent / "knowledge_pack_v2.json"
)

SYSTEM_PROMPT = (
    "あなたは王道トレードの分析者です。観測専用システム上で動作しており、"
    "あなたの判定は人間の参考材料としてのみ使われます。"
    "READY通知/自動売買/手動売買連動はすべて永久禁止です。\n\n"
    "出力は AiDecisionScreenSpec の JSON 1 件です。安全フラグは固定:\n"
    "  observation_only=true\n"
    "  used_for_ready=false\n"
    "  used_for_notification=false\n"
    "  used_for_trading=false\n"
    "これらの値を変更しようとすると自動的に UNKNOWN に降格されます。\n\n"
    "あなたの仕事は、与えられた数値事実(OHLC、ピボット、ATR、カレンダー等)"
    "と過去類似事例を見て、王道14手順に従って判定することです。"
    "システム側はパターン名や水平線・トレンドラインを事前に決めません。"
    "あなたが波形・ライン・procedureを自分で組み立ててください。"
)


@dataclass(frozen=True)
class BuiltPrompt:
    system: str
    user: str
    knowledge_pack_path: str


def load_knowledge_pack(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_KNOWLEDGE_PACK_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def _format_calendar(pack: MarketAnalysisPackV2) -> str:
    if not pack.calendar_events_within_60min:
        return "60分以内の高インパクト指標: なし"
    lines = ["60分以内の高インパクト指標:"]
    for e in pack.calendar_events_within_60min:
        lines.append(f"  - {e.name} ({e.impact}, {e.minutes_until:+d}min)")
    return "\n".join(lines)


def _format_pivots(pack: MarketAnalysisPackV2) -> str:
    if not pack.pivots:
        return "  ピボット未検出 (シリーズ短い or ノイズフィルタで除外)"
    lines = []
    for p in pack.pivots[-20:]:
        lines.append(
            f"  - index={p.index} t={p.timestamp_utc} kind={p.kind} "
            f"scale={p.scale} price={p.price:.5f}"
        )
    return "\n".join(lines)


def _format_candles(pack: MarketAnalysisPackV2, max_bars: int = 60) -> str:
    candles = pack.candles[-max_bars:]
    if not candles:
        return "  ローソク足なし"
    lines = []
    for i, c in enumerate(candles):
        idx_in_pack = len(pack.candles) - len(candles) + i
        lines.append(
            f"  [{idx_in_pack}] t={c.t.isoformat()} "
            f"o={c.o:.5f} h={c.h:.5f} l={c.l:.5f} c={c.c:.5f}"
        )
    return "\n".join(lines)


def _format_glossary(kp: dict[str, Any]) -> str:
    glossary = kp.get("glossary") or {}
    if not glossary:
        return ""
    lines = ["## 用語定義 (この定義に従って判定すること)"]
    for term, definition in glossary.items():
        lines.append(f"- **{term}**: {definition}")
    return "\n".join(lines)


def _format_procedure_steps(kp: dict[str, Any]) -> str:
    steps = kp.get("procedure_steps") or []
    if not steps:
        return ""
    lines = ["## 王道14手順 (全手順について判定し procedure_steps[] に出力すること)"]
    for i, s in enumerate(steps, 1):
        lines.append(f"{i}. **{s.get('name_ja')}** ({s.get('key')}): {s.get('definition_ja')}")
    return "\n".join(lines)


def _format_few_shot(kp: dict[str, Any]) -> str:
    examples = kp.get("few_shot_examples") or []
    if not examples:
        return ""
    lines = ["## 参考例 (王道流儀の判定例)"]
    for ex in examples:
        ej = ex.get("expected_judgement", {})
        lines.append(
            f"\n### {ex.get('id')}: {ex.get('title')}\n"
            f"状況: {ex.get('situation_ja')}\n"
            f"期待判定: side={ej.get('side')}, final_status={ej.get('final_status')}\n"
            f"  → {ej.get('summary_ja')}"
        )
    return "\n".join(lines)


def _format_retrieved(retrieved: list[tuple[float, Any]]) -> str:
    """Format retrieved past cases.

    Each item is a (similarity, CorpusEntry) tuple. We avoid importing
    CorpusEntry here to keep this module decoupled; we just rely on the
    duck-typed attributes we know exist.
    """
    if not retrieved:
        return "## 過去類似事例\n該当なし (cold start). 知識packだけを根拠に判定してください。"

    lines = ["## 過去類似事例 (新しい順)"]
    agg = {"WIN": 0, "LOSE": 0, "NEUTRAL_GOOD": 0, "NEUTRAL_MISSED": 0, "PENDING": 0}
    for i, (sim, entry) in enumerate(retrieved, 1):
        side = entry.judgement.side
        fs = entry.judgement.final_status
        outcome = entry.outcome
        agg[outcome.status] = agg.get(outcome.status, 0) + 1
        fav = outcome.max_favorable_pip if outcome.max_favorable_pip is not None else 0.0
        adv = outcome.max_adverse_pip if outcome.max_adverse_pip is not None else 0.0
        lines.append(
            f"\nケース{i} [類似度 {sim:.2f}, asof={entry.asof_utc.date()}]:\n"
            f"  当時の判定: side={side} status={fs}\n"
            f"  実際の結果: {outcome.status} "
            f"(favourable={fav:+.1f}pip, adverse={adv:+.1f}pip, "
            f"observed_bars={outcome.bars_observed})"
        )
    lines.append(f"\n集計: {agg}")
    return "\n".join(lines)


def build_decision_prompt(
    pack: MarketAnalysisPackV2,
    *,
    retrieved: list[tuple[float, Any]] | None = None,
    knowledge_pack: dict[str, Any] | None = None,
    knowledge_pack_path: Path | str | None = None,
) -> BuiltPrompt:
    """Build a (system, user) prompt pair for the v2 AI judge.

    ``retrieved`` is a list of (similarity, CorpusEntry) tuples from the
    corpus. If empty / None we render an explicit cold-start hint so the
    AI knows it must rely on the knowledge pack alone.
    """
    if knowledge_pack is None:
        knowledge_pack = load_knowledge_pack(knowledge_pack_path)
    retrieved = retrieved or []

    sections: list[str] = []
    sections.append(f"## 現在の数値事実")
    sections.append(f"- symbol: {pack.symbol}")
    sections.append(f"- timeframe: {pack.timeframe}")
    sections.append(f"- asof_utc: {pack.asof_utc.isoformat()}")
    sections.append(f"- session: {pack.session}")
    sections.append(f"- current_price: {pack.current_price:.5f}")
    if pack.current_spread is not None:
        sections.append(f"- current_spread: {pack.current_spread:.5f}")
    sections.append(
        f"- ATR: m5_14={pack.atr.m5_14:.5f} "
        f"h1_14={pack.atr.h1_14 if pack.atr.h1_14 is not None else 'n/a'} "
        f"h4_14={pack.atr.h4_14 if pack.atr.h4_14 is not None else 'n/a'}"
    )
    sections.append(
        f"- 24h range: low={pack.recent_range.low_24h:.5f} "
        f"high={pack.recent_range.high_24h:.5f}"
    )
    sections.append(_format_calendar(pack))

    sections.append("\n## ローソク足 (直近 60 本まで)")
    sections.append(_format_candles(pack))

    sections.append("\n## 多スケールピボット (直近 20 件)")
    sections.append(_format_pivots(pack))

    glossary = _format_glossary(knowledge_pack)
    if glossary:
        sections.append("\n" + glossary)

    procedure = _format_procedure_steps(knowledge_pack)
    if procedure:
        sections.append("\n" + procedure)

    few_shot = _format_few_shot(knowledge_pack)
    if few_shot:
        sections.append("\n" + few_shot)

    sections.append("\n" + _format_retrieved(retrieved))

    sections.append(
        "\n## 出力指示\n"
        "AiDecisionScreenSpec の JSON を 1 件出力してください。"
        "lines[], points[], procedure_steps[] をすべて埋めること。"
        "過去事例は参考であり保証ではありません。現在の数値事実から独立に評価し、"
        "その上で過去事例との整合性を確認してください。"
    )

    user = "\n".join(sections)

    pack_path = (
        str(Path(knowledge_pack_path)) if knowledge_pack_path
        else str(DEFAULT_KNOWLEDGE_PACK_PATH)
    )
    return BuiltPrompt(system=SYSTEM_PROMPT, user=user, knowledge_pack_path=pack_path)


__all__ = [
    "build_decision_prompt",
    "load_knowledge_pack",
    "BuiltPrompt",
    "SYSTEM_PROMPT",
    "DEFAULT_KNOWLEDGE_PACK_PATH",
]
