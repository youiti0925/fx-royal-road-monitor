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


def _format_indicators(pack: MarketAnalysisPackV2) -> str:
    """Embed doctrine indicators (SMA / BB / RSI / MACD / Fib / kiriban).

    These were previously left as ``UNKNOWN`` in every spec because the
    pack didn't carry them. Now that ``build_market_pack_v2`` computes
    them, the AI judge has actual numbers to feed into ma_alignment,
    indicator_environment, divergence_check and the round-number
    portion of horizontal_levels.
    """
    ind = pack.indicators
    out: list[str] = ["## コード計算済み指標 (判断基準として必ず使用すること)"]
    # Moving averages
    ma = ind.ma
    parts = []
    if ma.sma20 is not None: parts.append(f"SMA20={ma.sma20:.5f}")
    if ma.sma75 is not None: parts.append(f"SMA75={ma.sma75:.5f}")
    if ma.ema200 is not None: parts.append(f"EMA200={ma.ema200:.5f}")
    out.append(
        f"- MA: {', '.join(parts) if parts else '計算不能 (lookback 不足)'}. "
        f"current_price={pack.current_price:.5f}. "
        "ma_alignment step ではこの値を doctrine グランビル①〜⑧ と照合する事."
    )
    # Bollinger Bands
    if ind.bb is not None:
        bb = ind.bb
        squeeze = "squeeze" if bb.width_atr_ratio < 1.5 else "通常幅"
        out.append(
            f"- BB(20,2σ): lower={bb.lower:.5f} mid={bb.middle:.5f} upper={bb.upper:.5f} "
            f"width={bb.width_pip:.1f}pip ratio={bb.width_atr_ratio:.2f} ({squeeze}). "
            "indicator_environment / breakout step で使用."
        )
    else:
        out.append("- BB: 計算不能 (60本未満)")
    # RSI
    if ind.rsi14 is not None:
        zone = "売られすぎ(<30)" if ind.rsi14 < 30 else ("買われすぎ(>70)" if ind.rsi14 > 70 else "中立")
        out.append(
            f"- RSI14: {ind.rsi14:.1f} ({zone}). divergence_check で価格との逆行を確認."
        )
    # MACD
    if ind.macd is not None:
        m = ind.macd
        cross = "ゴールデンクロス気味" if m.histogram > 0 else "デッドクロス気味"
        out.append(
            f"- MACD: macd={m.macd:.5f} signal={m.signal:.5f} hist={m.histogram:+.5f} "
            f"({cross}). divergence_check で使用."
        )
    # Fib
    if ind.fib is not None:
        f = ind.fib
        out.append(
            f"- Fib (auto, direction={f.direction}): "
            f"anchor_high={f.anchor_high:.5f} anchor_low={f.anchor_low:.5f}. "
            f"50%={f.fib_500:.5f}  61.8%={f.fib_618:.5f}  78.6%={f.fib_786:.5f}. "
            "fibonacci_zone step ではプライムゾーン (50-61.8%) 帯到達か必須確認."
        )
    # Kiriban
    if ind.round_numbers_nearby:
        rns = " / ".join(f"{r:.5f}" for r in ind.round_numbers_nearby)
        out.append(
            f"- キリ番 (50pip 粒度, 80pip 半径): {rns}. "
            "horizontal_levels の重要度4フィルター ③ (キリ番接近) で使用."
        )
    return "\n".join(out)


def _format_structure_annotation(pack: MarketAnalysisPackV2) -> str:
    """Embed deterministic code-detected structure into the prompt.

    Why this exists
    ---------------
    The AI judge has two structural weaknesses that bite this domain:
      §2.A.1 no visual cortex — cannot "see" multi-touch trendlines or
        parallel channels in the pivot polyline.
      §2.B.9 no combinatorial search — does not enumerate (n choose 2)
        pivot pairs to find best-fit lines.

    See ``docs/SPEC.md`` for both. The countermeasure (validator F15/F16)
    catches AI outputs that don't reference what code found, but a
    cleaner approach is to put what code found in front of the AI as
    part of the prompt — the AI then *selects* from candidates rather
    than *searching* for them.

    This function calls :func:`structure_detector.summarize_structure`
    on the pack's pivot list and renders a structured annotation block
    plus explicit must-include / must-not-do rules tied to F15/F16.
    """
    # Late import to avoid a hard dep if structure_detector is missing.
    from fx_monitor.live.structure_detector import summarize_structure

    summary = summarize_structure(pack.pivots)

    out: list[str] = []
    out.append("## コード検出済み構造 (探索責任は code 側で完了)")
    out.append("")
    out.append(summary.to_text_annotation())
    out.append("")
    out.append("### この情報の使い方 (重要)")
    out.append(
        "- 上の HIGH TL / LOW TL / Channel / Pattern / Dow は code が "
        "全 pivot 組合せを enumerate して算出した確定値です。"
        "AI が改めて pivot list から探索する必要はありません。"
    )
    out.append("")
    out.append("### 必須要件 (validator F15 / F16 と連動)")
    out.append(
        "- **F15**: 上の `HIGH TL` または `LOW TL` の最も touches が多い候補に対応する "
        "斜めトレンドラインを `spec.lines` に必ず含めること "
        "(start_index / end_index / start_price / end_price をすべて埋める). "
        "対応とは: 検出された slope と spec の slope の差が 0.3 pip/bar 以内、"
        "endpoint の index 差が 5 bar 以内."
    )
    out.append(
        "- **F16**: 上の `Channel` で `upper.touch_count + lower.touch_count >= 7` の "
        "channel が検出されている場合、`spec.side` は `NEUTRAL` でなければならない. "
        "`final_status` は `WAIT_BREAKOUT` 推奨. channel 内のタッチを directional な "
        "BUY/SELL setup と扱うのは doctrine 違反 (saved time 狙いの反復敗因)."
    )
    out.append(
        "- 検出された Pattern (double_top / head_and_shoulders / triangle 等) は "
        "spec.pattern_label_ja に反映する事. AI が独自に pattern を上書きする場合は "
        "spec.lines / spec.points で具体的に裏付ける根拠を示すこと."
    )
    return "\n".join(out)


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
    n = len(steps)
    lines = [f"## 王道{n}手順 (全手順について判定し procedure_steps[] に出力すること)"]
    for i, s in enumerate(steps, 1):
        lines.append(f"{i}. **{s.get('name_ja')}** ({s.get('key')}): {s.get('definition_ja')}")
    return "\n".join(lines)


def _format_principles(kp: dict[str, Any]) -> str:
    """Render the higher-order doctrine so the AI applies them as constraints
    on top of the per-step procedure.

    v4 ordering puts ``htf_supremacy`` first because it is the
    user-stipulated top-level rule: lower-timeframe judgement is never
    permitted without an explicit higher-timeframe scan.
    """
    principles = kp.get("principles") or {}
    if not principles:
        return ""

    out: list[str] = ["## 王道判定の上位原則 (procedure_steps の上に必ず適用)"]

    htf = principles.get("htf_supremacy")
    if htf:
        out.append("\n### 【最上位原則 1/2】上位足の絶対的優位性 (HTF Supremacy) — テクニカル軸")
        out.append(htf.get("description_ja", ""))
        layers = htf.get("mandatory_layers", [])
        if layers:
            out.append(f"  必須スキャン階層: {' → '.join(layers)}")
        for rule in htf.get("rules", []):
            out.append(f"  - {rule}")

    fundamentals = principles.get("fundamentals_supremacy")
    if fundamentals:
        out.append("\n### 【最上位原則 2/2】ファンダメンタルの絶対的優位性 (Fundamentals Supremacy) — イベント軸")
        out.append(fundamentals.get("description_ja", ""))
        checks = fundamentals.get("mandatory_checks", [])
        if checks:
            out.append("  必須確認項目:")
            for c in checks:
                out.append(f"    - {c}")
        for rule in fundamentals.get("rules", []):
            out.append(f"  - {rule}")

    intervention = principles.get("intervention_2stage_trap")
    if intervention:
        out.append("\n### 為替介入の2段構え狩り (Intervention 2-Stage Trap)")
        out.append(intervention.get("description_ja", ""))
        for stage in intervention.get("stages", []):
            out.append(f"  - {stage}")
        amateur = intervention.get("amateur_action")
        pro = intervention.get("professional_action")
        if amateur:
            out.append(f"  ❌ 素人の行動: {amateur}")
        if pro:
            out.append(f"  ✅ プロの行動: {pro}")
        anti = intervention.get("anti_falling_knife_rule")
        if anti:
            out.append(f"  落ちてくるナイフ禁止: {anti}")
        v_pattern = intervention.get("v_recovery_pattern")
        if v_pattern:
            out.append(f"  急落V字回復パターン: {v_pattern}")

    crisis = principles.get("crisis_mode_strategy")
    if crisis:
        out.append("\n### クライシスモード戦略 (Crisis Mode Strategy)")
        out.append(crisis.get("description_ja", ""))
        triggers = crisis.get("trigger_conditions", [])
        if triggers:
            out.append("  発動条件 (いずれか1つで発動):")
            for t in triggers:
                out.append(f"    - {t}")
        for rule in crisis.get("rules", []):
            out.append(f"  - {rule}")

    triple = principles.get("triple_confluence_doctrine")
    if triple:
        out.append("\n### トリプル根拠 (Triple Confluence) — 本 doctrine の核心")
        out.append(triple.get("description_ja", ""))
        for axis in triple.get("axes", []):
            out.append(f"  - {axis}")
        thresholds = triple.get("thresholds", {})
        if thresholds:
            out.append("  根拠数の判断基準:")
            for k, v in thresholds.items():
                out.append(f"    - {k}: {v}")

    fib = principles.get("fibonacci_zone_doctrine")
    if fib:
        out.append("\n### フィボナッチ・ゾーン doctrine")
        out.append(fib.get("description_ja", ""))
        for r in fib.get("drawing_rules", []):
            out.append(f"  - 引き方: {r}")
        out.append("  レベル別戦略:")
        for ls in fib.get("level_strategy", []):
            out.append(
                f"    - {ls.get('level')} (リスク {ls.get('risk')}): {ls.get('strategy')}"
            )
        anti = fib.get("anti_pinpoint_rule")
        if anti:
            out.append(f"  ピンポイント禁止: {anti}")

    breakout = principles.get("breakout_3_signs")
    if breakout:
        out.append("\n### 高勝率ブレイクアウトの3サイン")
        out.append(breakout.get("description_ja", ""))
        for s in breakout.get("signs", []):
            out.append(f"  - {s}")
        stages = breakout.get("build_up_4_stages", [])
        if stages:
            out.append("  ビルドアップ4段階:")
            for st in stages:
                out.append(f"    - {st}")
        anti = breakout.get("anti_simple_break_rule")
        if anti:
            out.append(f"  禁止: {anti}")

    layered = principles.get("layered_analysis")
    if layered:
        out.append(f"\n### 階層分析")
        out.append(layered.get("description_ja", ""))
        for layer in layered.get("layers", []):
            tools = ", ".join(layer.get("tools", []))
            out.append(f"  - **{layer.get('name')}**: {tools}")

    env = principles.get("indicator_environment_filter")
    if env:
        out.append(f"\n### 指標は環境に応じて使い分ける")
        out.append(env.get("description_ja", ""))
        for r in env.get("rules", []):
            use = ", ".join(r.get("use", []))
            avoid = ", ".join(r.get("avoid", []))
            out.append(f"  - **{r.get('environment')}** → 使う: {use} / 避ける: {avoid}")
        rsi_warn = env.get("rsi_trap_warning")
        if rsi_warn:
            out.append(f"  RSI罠警告: {rsi_warn}")

    line_filter = principles.get("line_importance_filter")
    if line_filter:
        out.append("\n### ライン重要度4フィルター")
        out.append(line_filter.get("description_ja", ""))
        for f in line_filter.get("filters", []):
            out.append(f"  - {f}")

    reversal = principles.get("reversal_triple_motive")
    if reversal:
        out.append("\n### 反転の3独立動機")
        out.append(reversal.get("description_ja", ""))
        for m in reversal.get("motives", []):
            out.append(f"  - {m}")

    psych = principles.get("psychological_reading_3_layers")
    if psych:
        out.append("\n### 3層思考 (オーダー読解)")
        out.append(psych.get("description_ja", ""))
        for la in psych.get("layers", []):
            out.append(f"  - {la}")

    mtf = principles.get("mtf_principle")
    if mtf:
        out.append(f"\n### MTF (マルチタイムフレーム) 原則")
        out.append(mtf.get("description_ja", ""))
        for rule in mtf.get("rules", []):
            out.append(f"  - {rule}")

    conf = principles.get("confluence_axes")
    if conf:
        out.append(f"\n### コンフルエンス 5軸")
        out.append(conf.get("description_ja", ""))
        for axis in conf.get("axes", []):
            out.append(f"  - {axis}")
        thresholds = conf.get("thresholds", {})
        if thresholds:
            out.append("  軸数の判断基準:")
            for k, v in thresholds.items():
                out.append(f"    - {k}: {v}")

    inval = principles.get("invalidation_placement")
    if inval:
        out.append(f"\n### 損切り (インバリデーション) の置き方")
        out.append(inval.get("description_ja", ""))
        for r in inval.get("rules", []):
            out.append(f"  - {r.get('entry_method')}: {r.get('stop_placement')}")
        if inval.get("rr_minimum") is not None:
            out.append(f"  - **RR最低**: {inval.get('rr_minimum')} 未満のシナリオは HOLD に強制降格")
        principle_ja = inval.get("principle_ja")
        if principle_ja:
            out.append(f"  根本原則: {principle_ja}")

    checklist = principles.get("pre_trade_checklist")
    if checklist:
        out.append(f"\n### 自己診断 6項目チェックリスト (毎回最後に確認)")
        out.append(checklist.get("description_ja", ""))
        for i, item in enumerate(checklist.get("items", []), 1):
            out.append(f"  {i}. {item}")

    return "\n".join(out)


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
    """Format a single retrieval bucket.

    Each item is a (similarity, CorpusEntry) tuple.
    """
    if not retrieved:
        return ""

    lines = []
    agg = {"WIN": 0, "LOSE": 0, "NEUTRAL_GOOD": 0, "NEUTRAL_MISSED": 0, "PENDING": 0}
    for i, (sim, entry) in enumerate(retrieved, 1):
        side = entry.judgement.side
        fs = entry.judgement.final_status
        outcome = entry.outcome
        agg[outcome.status] = agg.get(outcome.status, 0) + 1
        fav = outcome.max_favorable_pip if outcome.max_favorable_pip is not None else 0.0
        adv = outcome.max_adverse_pip if outcome.max_adverse_pip is not None else 0.0
        lines.append(
            f"  ケース{i} [類似度 {sim:.2f}, asof={entry.asof_utc.date()}]: "
            f"side={side} {fs} → outcome={outcome.status} "
            f"(fav={fav:+.1f}pip, adv={adv:+.1f}pip)"
        )
    lines.append(f"  集計: {agg}")
    return "\n".join(lines)


def _format_multi_retrieved(modes: dict[str, list[tuple[float, Any]]]) -> str:
    """Format the v6 multi-mode retrieval output as labelled subsections.

    ``modes`` is the dict returned by ``JsonlVectorStore.search_multi_mode``.
    Empty buckets are still rendered (with a 'なし' note) so the AI knows
    we tried that lens and found nothing.
    """
    labels = {
        "generic": "数値類似 (any outcome)",
        "win_only": "数値類似 × 成功 (outcome=WIN)",
        "lose_only": "数値類似 × 失敗 (outcome=LOSE) — 同じ轍を踏まないように",
        "same_htf_context": "同じセッション/HTF文脈",
        "same_fundamentals": "同じファンダ環境 (高インパクト指標の有無一致)",
        "visual_similar": "視覚類似 (CLIP image embedding) — チャート形状ベース",
        "visual_win_only": "視覚類似 × 成功 (CLIP × WIN)",
        "visual_lose_only": "視覚類似 × 失敗 (CLIP × LOSE)",
    }
    out = ["## 過去類似事例 (5モード並走検索)"]
    any_present = False
    for key, label in labels.items():
        bucket = modes.get(key) or []
        out.append(f"\n### {label}")
        if not bucket:
            out.append("  該当なし。")
            continue
        any_present = True
        out.append(_format_retrieved(bucket))
    if not any_present:
        out.append(
            "\n注: 全モードで該当なし (cold start). 知識packと現在の数値事実だけを"
            "根拠に判定してください。"
        )
    return "\n".join(out)


def build_decision_prompt(
    pack: MarketAnalysisPackV2,
    *,
    retrieved: list[tuple[float, Any]] | None = None,
    retrieval_modes: dict[str, list[tuple[float, Any]]] | None = None,
    knowledge_pack: dict[str, Any] | None = None,
    knowledge_pack_path: Path | str | None = None,
) -> BuiltPrompt:
    """Build a (system, user) prompt pair for the v2 AI judge.

    ``retrieved`` is the legacy single-bucket retrieval (kept for
    backward compatibility). ``retrieval_modes`` is the v6 multi-mode
    output from ``JsonlVectorStore.search_multi_mode`` and takes
    precedence when supplied.
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

    sections.append("\n" + _format_indicators(pack))

    sections.append("\n" + _format_structure_annotation(pack))

    glossary = _format_glossary(knowledge_pack)
    if glossary:
        sections.append("\n" + glossary)

    principles = _format_principles(knowledge_pack)
    if principles:
        sections.append("\n" + principles)

    procedure = _format_procedure_steps(knowledge_pack)
    if procedure:
        sections.append("\n" + procedure)

    few_shot = _format_few_shot(knowledge_pack)
    if few_shot:
        sections.append("\n" + few_shot)

    if retrieval_modes is not None:
        sections.append("\n" + _format_multi_retrieved(retrieval_modes))
    elif retrieved:
        sections.append("\n## 過去類似事例 (新しい順)")
        sections.append(_format_retrieved(retrieved))
    else:
        sections.append(
            "\n## 過去類似事例\n該当なし (cold start). "
            "知識packと現在の数値事実だけを根拠に判定してください。"
        )

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
