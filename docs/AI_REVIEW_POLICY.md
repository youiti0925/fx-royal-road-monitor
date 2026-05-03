# AI Review Policy

## 1. AI に何をさせるか / させないか

### させる
- 与えた **知識パック** と **payload** と **画像** に基づいて、王道手順チェックを行う。
- `verdict / bias / confidence / reasons / disagreements / missing` を返す。

### させない
- 一般知識 / 最新情報 / 他通貨ペアからの推測。
- payload にない数値の創作 (ATR、スイング等の hallucination)。
- READY を出すかどうかの**最終決定**。AI は助言層であって、決定層ではない。

## 2. 必ず渡すもの (毎回・全部)

| # | 内容 | ソース |
|---|------|--------|
| 1 | 王道手順の知識パック | `docs/ROYAL_ROAD_KNOWLEDGE_PACK_v1.md` (生 markdown) |
| 2 | 判定基準の定義 | 同 §2 |
| 3 | READY OK/NG 条件 | 同 §2.1 / §2.2 |
| 4 | 出力 JSON schema | `src/fx_monitor/ai/schema.py` を JSON Schema 化したもの |
| 5 | 現在チャートの payload | `core/models.py` の `ChartPayload` |
| 6 | 現在チャート画像 | `render/chart_card_renderer.py` の出力 PNG |

「あとで省略する最適化」は **してはいけない**。毎回フル送信する。
プロンプトキャッシュは API 側で勝手に効くなら効かせる。

## 3. 二重レビューを採用する理由

- 単一 AI の hallucination / 一時的な性能ブレを相対化するため。
- 一致した時だけ READY にすることで、誤検知率を体感的に下げる。

これは精度の保証ではなく、**安全側に倒すための手続き** である。

## 4. プロバイダ独立性

- `openai_reviewer.py` / `claude_reviewer.py` は同一インターフェース (`Reviewer.review(payload, image) -> ReviewResult`) を実装する。
- どちらか一方が無効化されている場合、`AGREE_PASS` は成立しない (= READY を出さない)。
- 開発時 / CI では `mock_reviewer.py` を使用 (`AI_USE_MOCK=true`)。

## 5. 失敗時の挙動

- API エラー / タイムアウト / schema 不適合 → その reviewer の結果は `UNKNOWN` 扱い。
- 結果として `INSUFFICIENT` になり、READY は出ない。
- リトライは tenacity で 2–3 回まで。最終的に失敗してもクラッシュさせず、`UNKNOWN` を返す。
