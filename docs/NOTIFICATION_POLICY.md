# Notification Policy

## 1. 通知レベル

| level        | 条件                                                                                          | チャネル                       |
|--------------|-----------------------------------------------------------------------------------------------|--------------------------------|
| `READY`      | ルール `PASS` + 二重 AI 比較が `AGREE_PASS` + cooldown 外 + 重要指標 ±15 分外               | console + Discord + LINE       |
| `WATCH`      | ルール `PASS` + 比較が `AGREE_PASS` 以外 (例: `DISAGREE`, `AGREE_HOLD`)                       | console (静か)                 |
| `INFO`       | ルール `WAIT` / `WARN` で観察に値する場合                                                     | console (DEBUG ログ)           |
| `SUPPRESSED` | `BLOCK` / `INSUFFICIENT` / cooldown 中 / 指標直前 / payload 欠損                              | 通知しない (logs only)         |

## 2. 抑制 (suppression) ルール

- **cooldown**: 同一 `(symbol, timeframe, verdict=READY)` は `NOTIFY_COOLDOWN_SECONDS` 以内に
  再通知しない (デフォルト 900 秒 = 15 分)。
- **calendar guard**: 重要指標 ±15 分は `READY` を出さない (`SUPPRESSED`)。
- **AI 不一致**: OpenAI / Claude の verdict または bias が一致しないとき `READY` を出さない。
- **dry-run**: `DRY_RUN=true` のとき、Discord / LINE には送らずコンソールに preview のみ。

## 3. 通知本文 (READY)

- symbol / timeframe / timestamp(UTC)
- ルールエンジン verdict + 主な理由
- OpenAI verdict / bias / confidence / reasons (短く)
- Claude verdict / bias / confidence / reasons (短く)
- compare 結果 (`AGREE_PASS`)
- suggested invalidation / target (両 reviewer の中央値、無ければ omit)
- chart card 画像 (添付できるチャネルのみ)

## 4. 失敗時の挙動

- どれか 1 つの通知 backend が失敗してもクラッシュさせない。
- 失敗は WARNING ログに記録し、次の backend に進む。
- 全 backend が失敗した場合のみ ERROR を立てる。

## 5. AI を最終アクションにしない原則

通知を送るかどうかの**最終ゲートは `core/compare.py` と `notify/notifier.py` の決定論的コード**。
AI の出力はその入力の 1 つでしかない。AI が "送れ" と言っても、cooldown / calendar guard /
DRY_RUN を破ってはならない。
