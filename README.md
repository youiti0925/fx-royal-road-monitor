# fx-royal-road-monitor

5分単位で FX チャートを監視し、**王道手順 (royal road)** ルールで判定したうえで、
OpenAI と Claude の **二重 AI レビュー**を取り、結果を比較して通知するシステム。

## 役割分担

| repo | 役割 |
| ---- | ---- |
| `youiti0925/test` | 研究 / 検証 (バックテスト・リサーチ) |
| `youiti0925/fx-royal-road-monitor` (このリポジトリ) | 5分監視 + ルール判定 + 二重 AI レビュー + 比較 + 通知 |

このリポジトリでは **OANDA / paper / live / 自動売買は扱わない**。
通知 (Discord / LINE / コンソール) のみが出力チャネル。

## 最重要方針

AI に一般知識を期待しない。毎ターン必ず以下を payload としてプロンプトに渡す:

1. 王道手順の知識パック (`docs/ROYAL_ROAD_KNOWLEDGE_PACK_v1.md`)
2. 判定基準 `PASS / WAIT / WARN / BLOCK / UNKNOWN`
3. `READY` にしてよい / いけない条件
4. 出力 JSON schema (`src/fx_monitor/ai/schema.py`)
5. 現在チャートの payload (構造化数値)
6. 現在チャート画像 (vision 可のモデルにのみ)

詳細は `docs/AI_REVIEW_POLICY.md` を参照。

## ディレクトリ構成

```
src/fx_monitor/
  core/        models, rule_engine, compare
  knowledge/   knowledge pack loader
  ai/          schema, prompt_builder, openai_reviewer, claude_reviewer, mock_reviewer
  render/      chart_card_renderer
  notify/      notifier (base), console / discord / line backends
  app/         run_once, run_watch
docs/          knowledge pack & policies
tests/         pytest
.github/workflows/monitor.yml   5分 cron (現状は dry-run + テスト)
```

## クイックスタート

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # 値はローカルのみ。コミット禁止。
pytest
python -m fx_monitor.app.run_once   # 1 回だけ実行 (dry-run)
```

## やらないこと (明示)

- OANDA / paper / live / 自動売買
- 既存 `youiti0925/test` の `main` / PR #22 / PR #23 を触る
- AI を **final action** に使う (AI は助言層、最終判断はルール + 通知判定)
- API キーをコミットする

## Notification cards

`run_once` は (fixture mode の場合) 王道通知カード PNG を生成できます。

```env
FX_MONITOR_RENDER_CARD=true
FX_MONITOR_ATTACH_CARD=true
FX_MONITOR_CARD_PATH=out/notification_card.png
```

`FX_MONITOR_ATTACH_CARD=true` のとき、Discord は multipart `file=`、
LINE Notify は `imageFile=` で PNG を添付して送信します。
`DRY_RUN=true` のときは送信せず、生成画像のパスのみ stdout に出力します。

### Japanese fonts

通知カードは matplotlib で描画しますが、フォントファイルはこの repo に
**同梱しません**。CJK フォントはホスト側でインストールしてください。

Ubuntu:

```bash
sudo apt-get install fonts-noto-cjk
```

または、明示的に指定:

```env
FX_MONITOR_FONT_FAMILY=Noto Sans CJK JP
# あるいは絶対パス指定 (.ttf / .otf):
FX_MONITOR_CJK_FONT_PATH=/path/to/NotoSansCJKjp-Regular.otf
```

フォントが見つからなくても renderer は落ちません — 日本語ラベルだけ
豆腐 (□) になります。フォントファイルは絶対に commit しないでください。

## ステータス

初期 scaffold。実 API 呼び出し / 実チャート取得 / 実通知は未実装 (mock のみ稼働)。
通知カード PNG の生成と Discord/LINE への画像添付パスは実装済 (DRY_RUN
で安全側)。
