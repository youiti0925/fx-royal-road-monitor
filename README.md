# fx-royal-road-monitor v2

5分FX チャートに対する **王道判定** の観測専用システム。

- **AI** が王道14手順に沿って分析・画面設計を行う
- **コード** は数値事実の提供と事後検証のみ
- **過去データ** が教師 (RAG コーパス、自動 outcome ラベル)
- **コスト $0** 想定 (Claude Code subscription 内で完結、API キー不要)

## 安全方針(永久不変)

- 観測専用。**READY 通知 / 自動売買 / 手動売買連動はすべて永久禁止**
- AI 出力の `observation_only=true` / `used_for_*=false` は Pydantic と Layer 3 検証で多重強制
- ブローカー / 取引執行 / 通知ディスパッチコードは CI grep で検知 → 混入時は失敗
- 詳細: `.github/workflows/safety_lint.yml`

## アーキテクチャ

```
過去 OHLC アーカイブ (yfinance, 無料)
       ↓
candidate_filter で局面候補抽出 (offline)
       ↓
Claude Code 内で AI バッチ判定 (subscription, $0)
       ↓
60本後の price action から outcome 自動ラベル
       ↓
特徴ベクトル化 → JsonlVectorStore に保存
       ↓
ライブ (5分毎手動 or 自由なタイミング):
  数値事実 pack 構築 → 類似事例検索 → AI 判定 → Layer 3 検証 → 保存
```

## ディレクトリ構成

```
src/fx_monitor/
├── live/        数値事実層 (汚染禁止). pivots, market_pack, embedding, post_validate
├── corpus/      コーパス層. schema / store / outcome
├── offline/     オフラインバッチ. ohlc_archive, candidate_filter, batch_runner
├── ai/          AI 層. decision_screen_spec_schema, prompt_builder_v2, knowledge_pack_v2.json
├── render/      レンダラー. AI が出した spec を描画 (画面の scribe)
└── tools/       Claude Code 用 CLI. slash command が叩く

.claude/commands/
├── royal-road-check.md
├── royal-road-update-outcomes.md
├── royal-road-flag-dissent.md
├── royal-road-monthly-report.md
├── royal-road-dashboard.md
└── build-corpus-from-history.md
```

## セットアップ

```bash
git clone https://github.com/youiti0925/fx-royal-road-monitor
cd fx-royal-road-monitor
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev,market]      # market は yfinance を含む
pytest                             # テストが緑であることを確認
```

## 使い方 (Claude Code 内)

### 1. 過去データから辞書(コーパス)構築

```
/build-corpus-from-history --symbol EURUSD=X --start 2026-02-01 --end 2026-05-01
```

batch_size 件処理して止まる。subscription 枠が回復したら再実行で継続。
進捗は `data/progress/<symbol>_<timeframe>.json` に保存。

### 2. ライブ判定

```
/royal-road-check
```

最新OHLC を読み込み → 類似過去事例検索 → AI 判定 → 検証 → コーパス保存。

### 3. outcome 自動充填

```
/royal-road-update-outcomes
```

PENDING な判定で 60 本以上経過したものを yfinance で取得して outcome 計算。

### 4. その他

```
/royal-road-flag-dissent --id <entry_id> --note "..."   # 違和感フラグ
/royal-road-monthly-report                              # 月次自己診断
/royal-road-dashboard                                   # 静的HTML 再生成
```

## データの場所

| パス | 中身 |
|---|---|
| `data/corpus/<name>/entries.jsonl` | コーパスエントリ本体 |
| `data/corpus/<name>/vectors.npy` | 特徴ベクトル (linear cosine 検索) |
| `data/progress/*.json` | バッチ進捗ファイル |
| `data/pending_judgements/*` | `/royal-road-check` の途中状態 |
| `data/ohlc/*.parquet` | yfinance キャッシュ |
| `docs/live_dashboard/` | 静的ダッシュボード (file:// で開く) |

`data/` は `.gitignore` 管理(コミットしない)。

## 設計の要点

### コードでは無理な領域

王道 procedure の判定は決定論コードで完結しません。理由:

- **B.1 因果性**: 確認足判定に未来情報が要る
- **B.2 組み合わせ爆発**: 14手順×状態でルール量が破綻
- **B.3 過学習必然性**: パラメータ数 > 独立検証ケース数
- **B.4 非定常**: 市場レジーム変化に追従不能
- **B.5 形式仕様の不在**: 「ダウ崩れ」に唯一の定義がない
- **B.6 開いた状態空間**: 想定外イベントで未定義動作
- **B.7 タシット知識**: 熟練判断は言語化できない部分が大半

→ 手続き判断は AI、数値事実と事後検証はコード、という役割分担が現実解。

### コーパス = 学習ではなく辞書

LLM は推論時に学習しません(fine-tuning しない限り)。コーパスは **AI が毎回参照する外部辞書**。
`/royal-road-check` するたびに 1 ページ追加され、5 時間後に outcome が自動充填される。
使うほど分厚くなる構造。

## ライセンス

MIT
