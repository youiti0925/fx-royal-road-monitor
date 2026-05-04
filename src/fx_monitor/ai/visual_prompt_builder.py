"""Build the visual-review prompt (screen quality grading, not trading)."""

from __future__ import annotations

from dataclasses import dataclass

from .visual_review_schema import visual_review_schema_as_json

VISUAL_SYSTEM_INSTRUCTION = (
    "あなたはFX王道手順プレビュー画面のレビュー担当です。\n"
    "これは売買判定ではありません。READY通知判定でもありません。\n"
    "画像（decision_screen.png）を見て、画面が人間にとって分かりやすいか、\n"
    "観測専用 / READY通知不可 と明確に伝わるかだけを判定してください。\n"
    "\n"
    "確認項目:\n"
    "- 日本語UIになっているか\n"
    "- 観測専用 / READY通知不可 / 売買未使用 が明確か\n"
    "- 王道手順チェックの順番が分かるか\n"
    "- 波形 (P1/NL/P2/BR または B1/NL/B2/BR) が見えるか\n"
    "- ネックライン / WNL_D1 / WSL_D1 / WTP_D1 が見えるか\n"
    "- 構造ライン (SNL_D1 / SIL_D1 / STP_D1 / STL_D1) が見えるか\n"
    "- サポレジ帯が見えるか\n"
    "- BUY/SELL通知や発注画面と誤解されないか\n"
    "\n"
    "FAIL条件:\n"
    "- 英語だらけ\n"
    "- 線が読めない\n"
    "- 王道手順が分からない\n"
    "- READY通知可能に見える\n"
    "- 売買画面に見える\n"
    "\n"
    "出力は与えられたJSON schemaに厳密に従ったJSONのみ。\n"
    "JSONの前後に文章を書いてはいけません。\n"
    "summary_ja は日本語で書いてください。"
)


@dataclass(frozen=True)
class BuiltVisualPrompt:
    system: str
    user: str


def build_visual_review_prompt(*, context_summary: str = "") -> BuiltVisualPrompt:
    user = (
        "## 出力JSON schema\n"
        "```json\n"
        f"{visual_review_schema_as_json()}\n"
        "```\n\n"
        "## 画面の文脈\n"
        f"{context_summary}\n\n"
        "## タスク\n"
        "添付した画像（decision_screen.png）を確認し、上記JSON schemaに\n"
        "厳密に従ったJSONを1つだけ返してください。"
    )
    return BuiltVisualPrompt(system=VISUAL_SYSTEM_INSTRUCTION, user=user)


__all__ = ["build_visual_review_prompt", "BuiltVisualPrompt", "VISUAL_SYSTEM_INSTRUCTION"]
