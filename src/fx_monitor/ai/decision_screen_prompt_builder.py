"""Prompt builder for the AI-authored decision screen spec.

The AI is the analyst + screen designer. The system is the painter.
The AI must not be told what the answer is; it must reason from the
knowledge pack + market_analysis_pack and produce its own
``AiDecisionScreenSpec``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .decision_screen_spec_schema import decision_screen_spec_schema_as_json

DECISION_SCREEN_SYSTEM = (
    "あなたはFX王道手順の分析者であり、王道判定画面の設計者です。\n"
    "\n"
    "これは売買指示ではありません。\n"
    "これはREADY通知ではありません。\n"
    "これは観測専用の画面設計です。\n"
    "\n"
    "あなたの仕事は、与えられたローソク足・pivot・下書き構造・王道知識を読み、\n"
    "人間が見て納得できる王道判定画面の設計JSONを作ることです。\n"
    "\n"
    "システムが作った下書き線(pattern_levels_draft / wave_derived_lines_draft /\n"
    "structural_lines_draft 等) を盲信しないでください。\n"
    "必要なら「この線は弱い」「このトレンドラインは不自然」「ネックライン不明」\n"
    "と判断し、採用を見送ってください。\n"
    "\n"
    "必ず王道手順の順番で評価してください:\n"
    "  環境認識 → 上位足方向 → ダウ → 水平線 → トレンドライン → 波形 →\n"
    "  ブレイク → リターンムーブ → ローソク足確認 → ENTRY候補 → STOP候補 →\n"
    "  TP候補 → RR → イベント確認\n"
    "\n"
    "禁止事項:\n"
    "- READY通知を許可しない (used_for_ready は必ず false)\n"
    "- 売買可能に見せない (used_for_trading は必ず false)\n"
    "- 通知を許可しない (used_for_notification は必ず false)\n"
    "- 観測専用フラグを外さない (observation_only は必ず true)\n"
    "- 根拠が弱い線を採用しない\n"
    "- 採用した線には reason_ja を必ず書く\n"
    "- 不明な点は status=UNKNOWN にする\n"
    "\n"
    "出力は AiDecisionScreenSpec JSON のみ。\n"
    "JSONの前後に文章を書いてはいけません。\n"
    "summary_ja / reason_ja / market_story_ja は日本語で書いてください。"
)


@dataclass(frozen=True)
class BuiltDecisionScreenPrompt:
    system: str
    user: str


def build_decision_screen_prompt(
    *,
    market_analysis_pack: dict[str, Any],
    provider: str,
) -> BuiltDecisionScreenPrompt:
    pack_json = json.dumps(market_analysis_pack, ensure_ascii=False, indent=2)
    user = (
        "## 出力JSON schema (AiDecisionScreenSpec)\n"
        "```json\n"
        f"{decision_screen_spec_schema_as_json()}\n"
        "```\n\n"
        "## market_analysis_pack (王道分析の材料)\n"
        "```json\n"
        f"{pack_json}\n"
        "```\n\n"
        f"## あなたの provider 識別子\n"
        f"provider = \"{provider}\"\n\n"
        "## タスク\n"
        "上記の市場データと王道知識パックを読み、王道手順の各段階を\n"
        "評価し、観測専用の王道判定画面 (AiDecisionScreenSpec) を\n"
        "1つだけJSONで返してください。\n"
        "システムが作った下書き線を盲信しないでください。\n"
        "READY通知 / 通知 / 売買 / 取引執行 には絶対つなげない\n"
        "(used_for_ready=false / used_for_notification=false /\n"
        " used_for_trading=false / observation_only=true)。"
    )
    return BuiltDecisionScreenPrompt(system=DECISION_SCREEN_SYSTEM, user=user)


__all__ = [
    "build_decision_screen_prompt",
    "build_decision_screen_repair_prompt",
    "BuiltDecisionScreenPrompt",
    "DECISION_SCREEN_SYSTEM",
]


_REPAIR_SYSTEM = (
    DECISION_SCREEN_SYSTEM
    + "\n\n"
    + "前回のあなたの出力はユーザー確認用previewとして不十分でした。\n"
    + "validation_errors を読み、不足を埋めた完全な AiDecisionScreenSpec\n"
    + "JSON を返してください。具体的には以下を満たしてください:\n"
    + "- points を空にしない (王道判定に使う pivot を最低1つは出す)\n"
    + "- lines を空にしない (採用した線を最低1つは出す)\n"
    + "- procedure_steps を空にしない (王道15項目の主要な status を出す)\n"
    + "- observation_only=true / used_for_ready=false /\n"
    + "  used_for_notification=false / used_for_trading=false を必ず維持\n"
    + "- 不明な場合でも、利用可能な candles / pivots から「観測専用の\n"
    + "  参考線」として reason_ja 付きで出してください。\n"
    + "- それでも線が引けない場合は final_status=HOLD として\n"
    + "  procedure_steps を埋めてください (UNKNOWN のままにしない)。"
)


def build_decision_screen_repair_prompt(
    *,
    market_analysis_pack: dict,
    previous_spec: dict,
    validation_errors: list[str],
    provider: str,
) -> BuiltDecisionScreenPrompt:
    """Repair prompt for one retry pass.

    Includes the validation errors from the first attempt and the
    full prior spec so the model sees what it produced and what
    failed user-preview validation.
    """
    pack_json = json.dumps(market_analysis_pack, ensure_ascii=False, indent=2)
    prev_json = json.dumps(previous_spec, ensure_ascii=False, indent=2)
    errors_block = "\n".join(f"- {e}" for e in validation_errors) or "- (none)"

    user = (
        "## 出力JSON schema (AiDecisionScreenSpec)\n"
        "```json\n"
        f"{decision_screen_spec_schema_as_json()}\n"
        "```\n\n"
        "## あなたの前回の出力 (修正対象)\n"
        "```json\n"
        f"{prev_json}\n"
        "```\n\n"
        "## ユーザー確認用previewとしての validation_errors\n"
        f"{errors_block}\n\n"
        "## 市場データ材料 (再掲)\n"
        "```json\n"
        f"{pack_json}\n"
        "```\n\n"
        f"## あなたの provider 識別子\n"
        f"provider = \"{provider}\"\n\n"
        "## 修正タスク\n"
        "上記 validation_errors を解消した AiDecisionScreenSpec を\n"
        "1つだけJSONで返してください。\n"
        "points を空にしない / lines を空にしない /\n"
        "procedure_steps を空にしない /\n"
        "observation_only=true / used_for_ready=false /\n"
        "used_for_notification=false / used_for_trading=false /\n"
        "READY通知 / 通知 / 売買 / 取引執行 には絶対つなげない。"
    )
    return BuiltDecisionScreenPrompt(system=_REPAIR_SYSTEM, user=user)
