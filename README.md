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

## Market data feed

Initial feed support is **read-only**. There is no broker connection,
no OANDA, no live order, no paper trading.

Supported sources:

- `csv` — local OHLC file
- `yahoo` — optional `yfinance` (`pip install -e .[market]`)

CSV example:

```env
FX_MONITOR_FEED=csv
FX_MONITOR_CSV_PATH=tests/fixtures/ohlc_sample.csv
FX_MONITOR_SYMBOL=EURUSD=X
FX_MONITOR_TIMEFRAME=M5
```

## Draft payload from OHLC

CSV/Yahoo feed mode now builds an observation-only **draft payload**:

```
OHLC -> pivots -> rough support/resistance -> rough wave context
                                            -> RoyalRoadDraftPayload
                                            -> MonitorCase (draft)
```

Safety contract (enforced by tests + the rule engine):

- `observation_only = true`
- `used_in_final_action = false`
- `entry_plan.entry_status = HOLD`
- `royal_road_procedure_checklist.p0_pass = false`
- `evaluate_monitor_case()` returns `UNKNOWN` for any draft (and `WARN`
  if the draft is hand-edited to claim `READY`).
- Feed-mode `run_once` does **not** call OpenAI / Claude reviewers.
- Feed-mode `run_once` always ends in `Decision: SUPPRESSED`.

Use rich royal-road payload fixtures (`FX_MONITOR_FIXTURE_PATH=...`) for
READY notification tests.

Phase P1 rich draft keys are still observation-only:

- `pattern_levels_draft`
- `wave_derived_lines_draft`
- `structural_lines_draft`
- `support_resistance_v2_draft`
- `trendline_context_draft`
- `royal_road_procedure_checklist_draft`

They are not READY eligible. The dashboard's safety banner flips to
"CHECK SAFETY FLAGS" if `rich_draft.ready_eligible` or
`rich_draft.p0_pass` is ever true.

## Draft AI review mode

Feed mode can optionally send the observation-only draft payload to
OpenAI / Claude and append a JSONL summary for offline study:

```env
FX_MONITOR_REVIEW_DRAFT_WITH_AI=true
FX_MONITOR_REVIEW_LOG_PATH=out/review_log.jsonl
```

Hard contract:

- Draft AI review never dispatches notifications.
- Draft AI review never produces READY.
- `Decision: SUPPRESSED` is always printed.
- The JSONL record contains only summary fields (verdict / bias /
  confidence / a few reason lines) — no prompts, no raw payloads, no
  API keys.
- Even if the mock reviewer happens to return PASS in this mode, the
  draft path stays SUPPRESSED.

## Draft review report

Aggregate the JSONL draft AI review log into a Markdown + JSON report:

```bash
python -m fx_monitor.app.review_report \
    --log out/review_log.jsonl \
    --md out/review_report.md \
    --json out/review_report.json
```

The report counts top `missing` / `disagreements` / `reasons` from
OpenAI and Claude, plus rough pattern / pivot / zone stats. It is
**offline analysis only** — it is not used for READY decisions,
notifications, trading, or order execution.

## Scheduled draft review artifacts

`.github/workflows/monitor.yml` runs the observation-only draft review
on a 5-minute schedule (and on `workflow_dispatch`). On every scheduled
run it:

1. loads market data (`FX_MONITOR_FEED=yahoo`)
2. builds an observation-only draft payload from the OHLC
3. optionally asks OpenAI / Claude to review it (only when the
   corresponding repository secret is configured)
4. writes `out/review_log.jsonl`
5. generates `out/review_report.md` and `out/review_report.json`
6. uploads them as a workflow artifact (`draft-review-<run_id>`,
   14-day retention)

Push / pull-request runs only execute `pytest`. The draft-review job
is gated by `if: github.event_name == 'schedule' || github.event_name
== 'workflow_dispatch'`.

Safety contract (pinned by `tests/test_workflow_static.py`):

- `DRY_RUN=true`
- No READY notification from draft mode
- No Discord / LINE dispatch
- No OANDA
- No live / paper trading
- No order execution
- No font / API-key files committed

### Diagnostics artifact

Each scheduled draft-review run also writes:

```
out/diagnostics.json
```

It records:

- feed source / symbol / timeframe / candle count / warnings
- draft pivot / zone / rough-pattern counts + observation-only flag
- rule verdict / bias / reasons
- AI reviewer verdicts (or `"not_run"` when the review is skipped)
- compare result
- decision level (`SUPPRESSED`)
- safety flags (`ready_allowed=false`, `dispatch_called=false`,
  `dry_run`)

Secrets, tokens, API keys, webhooks, prompts, and raw payloads are
**not** stored — `write_diagnostics()` redacts any key matching
`api_key` / `token` / `secret` / `webhook` (case-insensitive)
recursively before write.

### Draft review dashboard

The scheduled workflow also writes:

```
out/dashboard.html
```

It combines `out/diagnostics.json` and `out/review_report.json` into a
single static HTML page (no JS, no external resources). The top of the
page shows a coloured safety banner — green ("SAFE: offline analysis
only") when every safety flag is correct, red ("CHECK SAFETY FLAGS")
otherwise. Below it: feed / draft / rule / OpenAI / Claude / compare /
decision cards plus top OpenAI / Claude `missing` and `disagreements`
tables.

The dashboard is **offline-only** and is not used for:

- READY decisions
- notifications
- trading
- order execution

Generate manually:

```bash
python -m fx_monitor.app.dashboard \
    --diagnostics out/diagnostics.json \
    --summary out/review_report.json \
    --html out/dashboard.html
```

Planning documents:

- [Scheduled Draft Review Runbook](docs/RUNBOOK_SCHEDULED_DRAFT_REVIEW.md)
- [Draft to Rich Payload Promotion Plan](docs/DRAFT_TO_RICH_PROMOTION_PLAN.md)

## ステータス

初期 scaffold。実 API 呼び出し / 実チャート取得 / 実通知は未実装 (mock のみ稼働)。
通知カード PNG の生成と Discord/LINE への画像添付パスは実装済 (DRY_RUN
で安全側)。マーケットデータ feed は CSV / Yahoo (optional) の入口のみ
実装済 — feed だけでは READY を出さない。
