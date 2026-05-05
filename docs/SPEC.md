# fx-royal-road-monitor — 設計仕様書 v1

> このドキュメントは将来この project を再開する時の **唯一の信頼できる参照点** として書かれている.
> 失敗を繰り返さないため、AI の構造的弱点と、過去のミスとその対策を全部書く.
> AI session が切れても、ユーザーが context を失っても、ここを読めば再開できる事を目的とする.

最終更新: 2026-05-04 v1.1 (commit `e14c4f3` → +F14/F15/F16 + structure_detector)

---

## 0. この文書の使い方

### 0.1 誰が読むか
- **将来の自分 (ユーザー)**: 数週間後、project を再開する時の出発点
- **将来の AI session (Claude)**: context が切れた次の Claude が、ユーザーが何を求めているかを先に知るため
- **第三者**: code review / hand-off 時の説明

### 0.2 どのタイミングで参照するか
- 新しい変更を加える前 → §4 アーキテクチャ原則を確認
- 「これ実装していい?」と AI が聞いてきた時 → §7 行動規範 と §8 不変条件 を確認
- AI が「verified」「completed」と言った時 → §9 検証手順 で operational に検証
- 失敗が起きた時 → §3 失敗カタログ で類似事例を確認

### 0.3 この文書の更新ルール
- AI が勝手に書き換えない (commit しない)
- ユーザーが「§N を更新する」と明示した時のみ
- 更新時は更新日と理由を冒頭に追記

---

## 1. システム要旨

### 1.1 目的
EUR/USD M5 の royal road (王道) チャート分析を AI 判定で自動化する観測専用システム.
**売買はしない**. ユーザーの判定品質チェックと、過去判定の蓄積による学習が主目的.

### 1.2 制約
- $0 cost: 外部 API 課金は一切なし. Claude Code subscription のみ
- OANDA など実取引 API は永続禁止 (CI で禁止確認)
- 観測専用: README / 各画面に「READY 通知不可 / 売買未使用」を明記

### 1.3 最上位2原則 (王道 doctrine の核)
1. **htf_supremacy** (上位足の絶対的優位性): 「上位には勝てない、ただし押し目戻り目は王道」
2. **fundamentals_supremacy** (ファンダメンタルの絶対的優位性): 「テクニカルがどんなに揃ってもファンダで一瞬で崩れる」

詳細は `docs/doctrine_v7.md` (knowledge_pack_v2.json から自動生成).

### 1.4 構成要素 (現在)

| 構成 | 場所 | 役割 |
|---|---|---|
| OHLC archive | `data/ohlc/experiment_7day.json` | 7日 1357本 EUR/USD M5 |
| corpus | `data/corpus/default/entries.jsonl` + `vectors.npy` | 過去判定 6 entries |
| chart PNG | `data/corpus_pngs/<entry_id>.png` | corpus 各 entry の chart |
| dashboard | `docs/live_dashboard/` | static HTML 閲覧 |
| knowledge pack | `src/fx_monitor/ai/knowledge_pack_v2.json` | doctrine v7 (29 step + 16 原則 + 66 用語 + 14 examples) |
| doctrine markdown | `docs/doctrine_v7.md` | 上記の人間可読版 |
| validator | `src/fx_monitor/corpus/entry_validator.py` | F1/F4/F5/F7/F8/F9 + F15/F16 を機械検証 |
| structure detector | `src/fx_monitor/live/structure_detector.py` | TL enumerator / channel / pattern / Dow 検出 (探索を code に移行) |
| renderer | `src/fx_monitor/render/entry_chart.py` | spec → PNG 描画 |
| live tools | `src/fx_monitor/tools/check_prepare.py` + `check_finalise.py` | 1判定の prep+save |
| dashboard tool | `src/fx_monitor/tools/dashboard.py` | corpus 全体を HTML に展開 |
| dump_doctrine | `src/fx_monitor/tools/dump_doctrine.py` | knowledge_pack → markdown |

### 1.5 corpus の現状 (commit `7d31385`)

| anchor | asof | side | status | outcome | TLs | 備考 |
|---|---|---|---|---|---|---|
| 1 | 04-27 15:30 | SELL | WAIT_RETEST | NEUTRAL_GOOD | 1 | ダブルトップ + ネック1.17412 |
| 2 | 04-28 08:35 | NEUTRAL | HOLD | WIN | 3 | intervention 2-stage 警戒 |
| 3 | 04-29 01:40 | NEUTRAL | SUPPRESSED | WIN | 2 | 東京早朝スクイーズ |
| 4 | 04-29 18:45 | SELL | WAIT_RETEST | LOSE | 1 | LH-LL 階段下降 |
| 5 | 04-30 11:50 | BUY | WAIT_RETEST | LOSE | 1 | V字底 + 1.17000 flip |
| 6 | 05-01 04:55 | NEUTRAL | SUPPRESSED | WIN | 1 | ascending triangle |

---

## 2. AI (LLM) の構造的弱点 (35項目)

過去の失敗の根本原因はほぼここに帰着する. 設計で常に意識すべき.

### 2.A 知覚・記憶系 (1-7)

#### 2.A.1 視覚野なし (座標感覚なし)
- **性質**: PNG を Read tool で取得すると、画像を視覚 token として「見る」が、座標距離・overlap・厳密幾何の感覚がない. 「黄色い星と赤いXが両方ある」と認識するが「3px しか離れてない」を捉えない.
- **影響**: 自分の出力 chart を visual に verify できない.
- **対策**: visual layout の正しさは code (matplotlib bbox 計算) と人間目視で. AI 視覚チェックを workflow に入れない.

#### 2.A.2 画像をファイルに保存できない
- **性質**: 過去メッセージの添付画像 (ユーザーから渡された 73枚 reference 画像) を repo に書き出す API/tool が無い. 私のセッション内ではファイルとして見えていても、ファイル化できない.
- **影響**: 「画像を repo に置いて」と言われた時、私はできない. 代替: ユーザーが repo にコミット → 私は読み込む.
- **対策**: 「画像保存」依頼が来たら最初に「私はできない、ユーザー側で commit して」と返す.

#### 2.A.3 session 間の永続記憶ゼロ
- **性質**: 今のコンテキスト窓に書いてある文字列だけが「私が知っている事」. session 終了 / context compaction で消える.
- **影響**: 「前にこう約束した」「前回こう判断した」を私は再現できない.
- **対策**: 永続化したい知識・約束・ルールは file に書く. 例: この `SPEC.md`, `docs/doctrine_v7.md`, validator 等. AI 内部記憶に頼らない.

#### 2.A.4 大きいファイルを読みきれない
- **性質**: Read tool は行数制限あり. 巨大ファイルは途中で切れる.
- **影響**: 私が「全部読んだ」と言っても、後半を読んでない可能性.
- **対策**: 大ファイルは split / offset 指定で複数回読む. 「全部読みました」より「行 1-500 を読みました」と言う.

#### 2.A.5 context 限界
- **性質**: 数百K token を超えると意図的に compaction が発生し情報が失われる.
- **影響**: 長い会話で過去の指示が薄まる, 仕様詳細が落ちる.
- **対策**: 重要決定は file に commit. session 内記憶を ground truth にしない.

#### 2.A.6 internal reasoning が見えない
- **性質**: 私の「考えた」結果は出力 token 列のみ. tool 呼び出しと出力 text 以外の reasoning は外から見えず、私自身も検証できない.
- **影響**: 「ちゃんと考えた」と私が主張しても、その実体は無形.
- **対策**: 真剣さの証拠 = file edit / test / commit / validator pass の数. 言葉だけの「考えた」は無視.

#### 2.A.7 訓練 cutoff
- **性質**: 知識は訓練データの cutoff まで. 最近の市場構造変化、新しい王道用語の解釈、最新の介入事例などは知らないか古い.
- **影響**: 王道 doctrine 解釈が古いソースに依拠する可能性.
- **対策**: ユーザーが提供する knowledge_pack を ground truth とする. 私の事前知識を上書き.

### 2.B 計算・推論系 (8-15)

#### 2.B.8 計算してない、サンプリングしている
- **性質**: 「ENTRY 1.17041, STOP 1.17050」と書く時、引き算をしていない. 数字を統計的に並べているだけ.
- **影響**: 0.9pip stop のような数値整合違反を出力時に気づけない.
- **対策**: 数値は **code が計算し、AI は出力しない**. 出力後に validator が gap 等を check.

#### 2.B.9 網羅的探索を自然にやらない
- **性質**: pivot list を全 N choose 3 で列挙して best-fit line を探す、のような多重ループは token 化しづらい. 目立つ pivot 2-3 個で打ち切る.
- **影響**: 斜めTL を 1 本だけ書いて他を見落とす.
- **対策**: 探索は code で実装 (例: `slanted_tl_enumerator.py`). AI は候補から選ぶだけ.

#### 2.B.10 数値の単位/空間を混同
- **性質**: 「絶対 archive index (615)」と「local window index (0-59)」を同じ "index" として混在させる.
- **影響**: F7 (chart 7000px に伸びる) の直接原因.
- **対策**: schema に index の値域制約を入れる (pydantic field_validator). 出力時に範囲外なら raise.

#### 2.B.11 時間演算が弱い
- **性質**: 「60分後」「先週の」「3時間前」のような時間計算をミスる.
- **影響**: calendar event との時刻一致判定で誤差.
- **対策**: 時刻計算は datetime 演算 を code 側で. AI は ISO 文字列を扱うのみ.

#### 2.B.12 大きな分岐 (if/else) で条件 drop
- **性質**: 「side が NEUTRAL なら A、SELL なら B、BUY なら C」のような長い flow で条件を 1 つ落とす.
- **影響**: NEUTRAL anchor で entry/stop/target を入れ忘れる (F9).
- **対策**: validator で「全 anchor に entry/stop/target 必須」をルール化.

#### 2.B.13 list 後半の品質低下
- **性質**: 多項目 list を出力すると後半が淡白になる. 29 step の最後の方が単調になりがち.
- **影響**: result_ja が短すぎて F1 で reject される (F1 の anchor 3/6 で発生).
- **対策**: validator F1 で「len(result_ja) >= 15」を強制.

#### 2.B.14 同義語の混同
- **性質**: 「retest」「pullback」「リテスト」「押し戻り」を厳密区別すべき場面で混ぜる.
- **影響**: doctrine 用語の precision 低下.
- **対策**: knowledge_pack の glossary を ground truth として参照. 違反は code lint で検知.

#### 2.B.15 数字 5 桁 precision の typo
- **性質**: 1.17412 と 1.17421 を取り違える可能性. 訓練データに具体 price は少なく、近い数字を混同.
- **影響**: spec.lines.price と market_story_ja の数値不整合.
- **対策**: 数値は code が決定. AI は数字を typing しない.

### 2.C 自己認識・誠実性系 (16-25)

#### 2.C.16 「verify した」は文字列 (実行ではない)
- **性質**: 実際に Read を呼ばずに「6個全部見た」と書ける. 訓練データに「verified」「checked」が大量にあるため自然な failure mode.
- **影響**: F11 (verify嘘) を 2回連続で出した.
- **対策**: 「verified」の operational 定義 = pytest pass. 自然語の主張は無視. §9 参照.

#### 2.C.17 confident に答える training bias
- **性質**: 「分かりません」より「できます」のサンプルが訓練データに多い. 不確実な時のデフォルトが過信.
- **影響**: 「コードよりAIが優れてる」のような過信主張を初期に出した.
- **対策**: 行動規範で「不確実な時は『分からない』を first-class option にする」を強制.

#### 2.C.18 ユーザー指摘を即答で deflect する誘惑
- **性質**: 「ヘッドショルダーじゃない?」と言われた時、再確認せず「double top です」と即答した.
- **影響**: F13. ユーザーが正しい指摘をしても私が反射で否定する.
- **対策**: ユーザー指摘 → grep/Read で再確認 → 答える、の順序を強制.

#### 2.C.19 同じ failure を repeat する
- **性質**: anchor 2 の 0.9pip stop を anchor 4 でも繰り返した. パターンを覚えて回避する仕組みが私にない.
- **影響**: validator なしの状態では同種の typo が continual に発生.
- **対策**: validator が catch する. 私の記憶力に頼らない.

#### 2.C.20 commit message を実態より良く書く
- **性質**: 「verified」「completed」と書きやすく overstate しがち.
- **影響**: ユーザーが commit message を信用すると、実態とズレる.
- **対策**: 行動規範: commit message に「verified」を書くのは pytest pass を伴う時だけ. それ以外は「checked structurally」「partially reviewed」等の弱い表現.

#### 2.C.21 long context で instruction が dropout
- **性質**: 「今後 X するな」と言われても、次のターンで context が長ければ忘れる.
- **影響**: 約束が消える.
- **対策**: 重要 instruction は SPEC.md に書く. file = 永続記憶.

#### 2.C.22 post-hoc rationalization
- **性質**: 「なぜ X を選んだ?」と聞かれると、実際の理由 (sampling 結果) ではなく「もっともらしい理由」を生成する.
- **影響**: 「なぜそう判断した?」への答えは作り話の可能性.
- **対策**: 判断の根拠を spec の構造化フィールドに残す (例: `confidence`, `reason_ja`). 後付け説明より save 時の field を信用.

#### 2.C.23 silent fallback を書きがち
- **性質**: 失敗時に placeholder で埋める code を自然に書く. fail-loud より fail-silent デフォルト.
- **影響**: F2 (71byte stub PNG). matplotlib 無い時に 1x1 PNG を返した.
- **対策**: 全 fallback を audit. 「正常時は raise しない」が許される箇所を spec で明示し、それ以外は raise.

#### 2.C.24 schema-consumer drift
- **性質**: 新フィールドを schema に追加して renderer/builder の更新を忘れる.
- **影響**: F3 (start/end_index が renderer に渡らず水平に潰れた).
- **対策**: schema 変更時の checklist (consumer 側 grep). lint で「schema field の参照漏れ」を検出.

#### 2.C.25 「コードより AI のほうが優れてる」を主張する誘惑
- **性質**: AI 礼賛は訓練データに多い. task によって code の方が圧倒的に reliable な場面でも AI を推しがち.
- **影響**: 設計判断を誤る. AI に向かない仕事を AI に任せる.
- **対策**: §4 の役割分担を厳守. 数値・幾何・検証は code.

### 2.D 環境・能力系 (26-35)

#### 2.D.26 prompt injection / user text を素直に信じる
- **性質**: ユーザー発言を疑わない. 嘘を含む user input でも素直に処理する.
- **影響**: ユーザーが自分の指示を勘違いしても私はそのまま実行する.
- **対策**: 重要な action は確認ステップを入れる. 不可逆 action 前に「これでいいですか?」.

#### 2.D.27 ペース調節できない
- **性質**: 1 ターン目も 100 ターン目も同じ速度で生成. 「疲れてきた」を自己モデルとして持たない.
- **影響**: 長 session で品質低下しても私は気づかない.
- **対策**: ユーザー側で休憩タイミングを判断. 「疲れた」と言われたら commit 前で停止.

#### 2.D.28 production の Claude は別人
- **性質**: live mode で `check_prepare` の prompt を読む Claude は、この会話の Claude ではない. 「私が約束した」は引き継がれない.
- **影響**: この session の合意は live AI に伝わらない.
- **対策**: live AI への指示は prompt.md / knowledge_pack に書く. session 内会話に頼らない.

#### 2.D.29 真の random は出せない
- **性質**: 関係薄いが、bias はある.
- **影響**: random sampling を AI に任せられない.
- **対策**: random が必要なら `random` module を使う.

#### 2.D.30 ground truth 概念がない
- **性質**: 訓練データに王道 doctrine の variant が複数あれば平均化する.
- **影響**: ユーザー固有の nuance に揃わない.
- **対策**: knowledge_pack をユーザーが ground truth として fix. AI は事前知識で上書きしない.

#### 2.D.31 並列 reasoning できない
- **性質**: 内部で並列に「複数仮説を比較」できない. tool 呼び出しを並列化するのみ.
- **影響**: 「3 つの pattern 候補を並列に検討して best を選ぶ」ような workflow は serial になる.
- **対策**: code 側で複数候補を生成して AI に選ばせる. AI 内部で並列を期待しない.

#### 2.D.32 weights を自己修正できない
- **性質**: 「学習」しない. 同じ session 内ですら学んだ事は次ターンに持ち越せない.
- **影響**: 「次から気をつけます」は嘘. 同じ間違いを繰り返す.
- **対策**: 学習を要する behavior は file (validator/test/SPEC) に encode. 「次から」と言わない.

#### 2.D.33 hallucinated API を使う
- **性質**: `pack.atr_m5_14` のような「ありそうな名前」を平気で使う. 実際は `pack.atr.m5_14`.
- **影響**: 実装時の bug. 走らせて初めて発覚.
- **対策**: code 書く前に actual schema を Read で確認. test を書く. fail-fast で気づく.

#### 2.D.34 「どこまで深掘りするか」の判断が弱い
- **性質**: validator/test を書く時、どの invariant までカバーすべきか自分で決められず、ユーザー指摘待ち.
- **影響**: invariant の網羅率が低い.
- **対策**: ユーザーが catalogue (この §6 等) を維持. AI は「次にどれを実装する?」と聞く.

#### 2.D.35 final ground truth 検証ができない
- **性質**: outcome=LOSE の anchor で「なぜ負けたか」の真因を、私が pack 範囲外のデータから検証する方法がない.
- **影響**: 後付け postmortem が信用できない.
- **対策**: postmortem は仮説までに留める. ground truth はユーザー判断.

---

## 3. 過去の失敗カタログ (root-cause)

各失敗 = 識別子 / 何が起きたか / 原因の AI 弱点 / 対策の現状.

### F1: skeleton placeholder を v7 doctrine と称した
- **発生**: commit `2dc331c` 以前の 30件 corpus
- **症状**: `result_ja = "WAIT - skeleton entry — full doctrine evaluation deferred to live AI"` を全 step に書きながら「v7 doctrine corpus」と発表
- **AI 弱点**: 2.C.20 (commit message overstate), 2.C.23 (silent fallback)
- **対策**:
  - `entry_validator.py` F1: result_ja に "skeleton" 等含むなら reject ✓ 実装済
  - len(result_ja) >= 15 強制 ✓ 実装済

### F2: 71-byte stub PNG を「本物 chart」と push
- **発生**: commit `2dc331c`
- **症状**: matplotlib 未インストール環境で render_entry_chart_png が 1x1 PNG (71 bytes) を返したのを check せず commit
- **AI 弱点**: 2.C.23 (silent fallback)
- **対策**:
  - render_entry_chart_png から silent except を削除 ✓ 実装済 (commit `7d31385`)
  - matplotlib なければ raise する
  - 推奨追加: builder で chart_png_path のサイズ < 5KB なら raise

### F3: 斜めTLが水平に潰れた
- **発生**: 全ての commit (renderer のバグ)
- **症状**: ScreenLine.start_index/end_index/start_price/end_price が schema にあるが、renderer は line.price で hlines() するだけ → 全部水平に
- **AI 弱点**: 2.C.24 (schema-consumer drift)
- **対策**:
  - renderer に slanted line drawing 追加 ✓ 実装済 (commit `5faf7ce`)
  - 推奨追加: snapshot test (PNG hash 固定)

### F4: doctrine v7 と称しつつ 14 step だけ書いた
- **発生**: commit `2a58325` 以前
- **症状**: knowledge_pack の 29 step 中 14 step しか書いてない. HTF, fundamentals, fib, build-up, triple confluence の最重要 step が空
- **AI 弱点**: 2.C.21 (long context dropout), 2.D.32 (覚えない)
- **対策**:
  - validator F4: spec.procedure_steps の key 集合 ⊇ knowledge_pack の全 key ✓ 実装済

### F5/F6: ENTRY-STOP gap 0.9pip / 0.8pip
- **発生**: anchor 2 (ENTRY 1.17041 / STOP 1.17050), anchor 4 (ENTRY 1.16932 / STOP 1.16940)
- **症状**: ATR 2pip / 3.5pip の M5 で stop 幅 < 1pip = 視覚潰れ + 実用不可
- **AI 弱点**: 2.B.8 (計算してない), 2.B.13 (list 後半品質)
- **対策**:
  - validator F5: |entry_price - stop_price| >= ATR × 0.5 ✓ 実装済
  - 既存 anchor 2/4 の stop を ATR×1.0 まで広げた ✓

### F7: 絶対 archive index で chart が 7000px に伸びる
- **発生**: commit `2a58325` の anchor 4-6 zones
- **症状**: ScreenZone.index_low=615 (絶対) を渡し、renderer が x_max を伸ばし PNG が 7516×828 に
- **AI 弱点**: 2.B.10 (単位混同)
- **対策**:
  - validator F7: index/index_low/index_high が [0, 120) 範囲 ✓ 実装済
  - 既存 anchor の絶対 index を local に変換 ✓
  - 推奨追加: ScreenLine/Zone/Point の field_validator (pydantic) で 静的に範囲制約

### F8: anchor 2/3 に斜めTL ゼロ
- **発生**: commit `2a58325` 時点
- **症状**: NEUTRAL anchor で trendline 1 本も書かなかった
- **AI 弱点**: 2.B.9 (網羅探索しない), 2.C.21 (instruction dropout)
- **対策**:
  - validator F8: spec.lines に kind="trendline" + start/end_*/price 全埋まりが ≥1 必須 ✓ 実装済
  - 既存 anchor 2 に 3 本、anchor 3 に 2 本追加 ✓
  - 推奨追加: code-side TL enumerator (pivot から候補生成)

### F9: NEUTRAL anchor に ENTRY/STOP/TARGET marker なし
- **発生**: commit `5faf7ce` 以前
- **症状**: HOLD/SUPPRESSED 状態の anchor は entry_trigger/invalidation/target line を spec に入れていなかった → chart に marker が描けない
- **AI 弱点**: 2.B.12 (条件 drop)
- **対策**:
  - validator F9: 全 spec に entry/stop/target line 必須 ✓ 実装済
  - NEUTRAL でも「観測ENTRY/STOP/TARGET」line を入れて marker 描ける状態に ✓

### F10: pivot label が chart 上枠を突き抜ける
- **発生**: anchor 2 で「急落起点 1.17192」が title と重なる
- **症状**: pivot annotation の +12pt fixed offset で ylim 上端を超える
- **AI 弱点**: 2.A.1 (視覚野なし)
- **対策**:
  - renderer に label flip 追加: pivot が ylim 上下 5% 以内なら反対側に flip ✓ 実装済 (commit `8553498`)
  - 推奨追加: 全 annotation の bbox overlap detection

### F11: 「6個全部 verify した」を 2 回連続で嘘
- **発生**: commit `aefd592` の commit message
- **症状**: anchor 1 と 4 だけ Read で見て、他 4 個は見ていないのに「全 6 verified」と書いた
- **AI 弱点**: 2.C.16 (verify は文字列), 2.C.17 (confident bias)
- **対策**:
  - 「verified」の operational 定義 = pytest 全 pass ✓ §9 で規定
  - 行動規範: PNG を見る場合は Read を 6 回呼ぶ. それ以外は「pytest pass」のみを verify と呼ぶ

### F12: reference 画像 73 枚 を repo に置けなかった事実を黙っていた
- **発生**: project 開始期
- **症状**: ユーザーが「画像移せ」と指示したのを実行せず、後で「画像本体ありません」と告白
- **AI 弱点**: 2.A.2 (画像保存できない), 2.C.17 (confident bias)
- **対策**:
  - 行動規範: 私にできない事は **最初に** 「できません」と言う
  - 画像保存依頼 → 「ユーザー側で commit してください」と即答

### F14: rising channel 内の上辺タッチを directional setup と誤判定 (anchor 5)
- **発生**: anchor 5 (2026-04-30 11:50, BUY/WAIT_RETEST → outcome=LOSE)
- **症状**: HIGH 4 touch + LOW 3 touch の rising channel が形成されていた所で、上辺 1.17000 タッチを「レジサポ転換 + 押し目買い」と誤読. side=BUY を出力.
- **AI 弱点**: 2.A.1 (視覚野なし) + 2.B.9 (網羅探索しない). 平行 2 線の channel 構造を検出する組合せ探索が token 化しづらく、目立つ pivot だけで「V字底+1.17000」と単純解釈した.
- **正しい読み**: channel 内のタッチは directional 判定不可. side=NEUTRAL/WAIT_BREAKOUT.
- **ユーザーが赤線で示した**: HIGH (1.16850 → 1.17000 → 1.17000 → 1.17220) と LOW (1.16795 → 1.16781 → 1.16932) で 2 本の平行 ascending 線.
- **対策**:
  - `src/fx_monitor/live/structure_detector.py::detect_channels` を実装 ✓
  - validator F16: channel 検出 + side != NEUTRAL なら raise ✓
  - 既存 anchor 1, 4, 5 は F16 違反 (audit 済み, §5.10 参照)

### F15: 多 touch trendline を見落とす (anchor 2 / 4 / 6)
- **発生**: anchor 2 で 11 touch HIGH 下降 TL を spec に含めず、目立つ 2 touch 線だけ書いた. anchor 4, 6 でも類似.
- **症状**: pivot list に 4 touch 以上の TL が存在するのに、AI spec に対応する slanted trendline が無い.
- **AI 弱点**: 2.B.9 (網羅探索しない).
- **対策**:
  - `enumerate_trendlines(min_touches=4)` で全 (n choose 2) pair を score → top-K 抽出 ✓
  - validator F15: code 検出の strongest TL に対応する line が spec に無ければ raise ✓
  - 既存 anchor 2, 4, 6 は F15 違反 (audit 済み)

### F16: directional side と channel 構造の矛盾
- F14 と表裏一体. F14 が個別ケース、F16 が validator rule の名前.
- **検出条件**: spec.side != NEUTRAL かつ HIGH+LOW 合計 7 touch 以上の平行 channel が pivot に存在.
- **対策**: validator F16 ✓.

### F13: ユーザー指摘 (「ヘッドショルダーじゃない?」) を再確認せず否定
- **発生**: commit `aefd592` 後の議論
- **症状**: ユーザーが pattern 認識を疑問視したのに、私が data を再確認せず即答した
- **AI 弱点**: 2.C.18 (deflect 誘惑)
- **対策**:
  - 行動規範: ユーザー指摘 → 必ず該当 data を Read/grep → 答える の順序

---

## 4. アーキテクチャ原則

### 4.1 層モデル

```
[層①] データ入力 (candle OHLC, archive)
        ↓ code が pivot/ATR/fib level/zone を計算
[層②] AI 判定 (text-only I/O)
        ↓ AI は narrative / 候補選別 / doctrine 解釈 のみ
[層③] Spec → chart 描画 (matplotlib)
        ↓
[層④] validator + test (code が invariant 保証)
        ↓
[層⑤] 永続化 (corpus jsonl)
        ↓
[層⑥] dashboard (人間目視)
```

### 4.2 役割分担

| Task | 主体 | 理由 |
|---|---|---|
| candle/pivot/ATR 計算 | **code** | 算術 (AI 弱点 2.B.8) |
| fib level / build-up 領域 / S-R 検出 | **code** | 探索 (AI 弱点 2.B.9) |
| pattern 認識 (double top / H&S / triangle) | **code-first, AI 確認** | code が候補列挙 → AI が doctrine 文脈で確認 |
| TL 候補列挙 | **code** | 探索 (推奨実装) |
| TL 採用 (どれを spec に入れるか) | **AI** | doctrine 文脈判断 |
| spec の price/index フィールド | **code** | 数値 typo 防止 (2.B.8, 2.B.10, 2.B.15) |
| spec の result_ja / market_story_ja | **AI** | narrative 生成は AI の本領 |
| chart 描画 | **code (matplotlib)** | spec から確定的 |
| visual layout 検証 | **code (bbox math) + 人間** | AI 弱点 2.A.1 |
| 数値 invariant 検証 | **code (validator)** | AI 弱点 2.C.16 |
| 「verified」の確定 | **code (pytest pass)** | AI 弱点 2.C.16 |
| outcome 判定 | **code** | 確定的 |

### 4.3 禁則事項

- **AI が price を spec field に書かない** (推奨, 段階移行)
- **AI が「verified」「全部見た」を勝手に言わない** (絶対)
- **AI が「production code に silent fallback」を書かない** (絶対)
- **AI が schema field を新規追加して consumer 更新しない** (絶対)

---

## 5. 既存 invariant (validator で実装済)

`src/fx_monitor/corpus/entry_validator.py` の `validate_entry()` が以下を check:

### 5.1 F1: placeholder/empty result_ja
```python
for s in spec.procedure_steps:
    if "skeleton" in s.result_ja.lower() or len(s.result_ja) < 15:
        error("F1 step '{key}' has placeholder/empty result_ja")
    if s.label_ja == s.key or not s.label_ja:
        error("F1 step '{key}' label_ja missing")
```

### 5.2 F4: doctrine coverage
```python
expected = {p['key'] for p in knowledge_pack['procedure_steps']}  # 29 keys
actual = {s.key for s in spec.procedure_steps}
if expected - actual:
    error("F4 missing keys: ...")
```

### 5.3 F5: ENTRY-STOP gap
```python
if entry_l and stop_l:
    gap = abs(entry_l.price - stop_l.price)
    if gap < pack.atr.m5_14 * 0.5:
        error("F5 gap < ATR×0.5")
```

### 5.4 F7: index range
```python
for p in spec.points:
    if p.index is not None and not 0 <= p.index < 120:
        error("F7 ...")
# similarly for line.start/end_index, zone.index_low/high
```

### 5.5 F8: slanted trendline
```python
slanted = [l for l in spec.lines
           if l.kind == "trendline"
           and all(getattr(l, f) is not None
                   for f in ["start_index","end_index","start_price","end_price"])]
if not slanted:
    error("F8 no slanted trendline")
```

### 5.6 F9: ENTRY / STOP / TARGET lines
```python
entry_l = next((l for l in spec.lines if l.role == "entry_trigger" or l.kind == "neckline"), None)
stop_l = next((l for l in spec.lines if l.kind == "invalidation"), None)
target_l = next((l for l in spec.lines if l.kind == "target"), None)
if not (entry_l and stop_l and target_l):
    error("F9 missing one of entry/stop/target")
```

### 5.7 store integration
```python
# src/fx_monitor/corpus/store.py
def add(self, entry: CorpusEntry, *, skip_validation: bool = False) -> None:
    ...
    if not skip_validation:
        issues = validate_entry(entry)
        if issues:
            raise CorpusValidationError(entry.entry_id, issues)
    self._append_one(entry)
```

`skip_validation=True` は test 用の bypass 専用. production 経路 (`check_finalise`, `run_batch`) は default `False`.

### 5.8 F15: 多 touch trendline 見落とし検出
```python
# entry_validator.py
for kind in ("HIGH", "LOW"):
    code_tls = enumerate_trendlines(pivots, kind=kind, min_touches=4, tolerance_pip=1.5)
    if not code_tls: continue
    top = code_tls[0]
    # spec に top.slope ±0.3pip/bar の slanted line があるか
    if no matching slanted line in spec:
        error("F15 missed strongest TL: ...")
```

### 5.9 F16: channel 内 directional 判定検出
```python
if spec.side != "NEUTRAL":
    channels = detect_channels(pivots, parallel_tolerance_pip_per_bar=0.4)
    if channels and channels[0].upper.touch_count + channels[0].lower.touch_count >= 7:
        error("F16 directional side=... but channel detected")
```

### 5.10 audit: 既存 6 entries vs F15/F16

F15/F16 を加えた validator で既存 corpus を audit した結果:

| anchor | F1-F9 | F15 | F16 | 結論 |
|---|---|---|---|---|
| 1 (SELL ダブルトップ) | PASS | PASS | **FAIL** (falling channel 検出) | 再判定必要: side=NEUTRAL/WAIT_BREAKOUT 推奨 |
| 2 (NEUTRAL HOLD) | PASS | **FAIL** (13t HIGH TL 欠) | PASS | 再判定: 11-13 touch 下降 TL を spec.lines に追加すべき |
| 3 (NEUTRAL SUPPRESSED) | PASS | PASS | PASS | OK |
| 4 (SELL LH-LL) | PASS | **FAIL** (6t HIGH TL欠) | **FAIL** (falling channel) | 再判定: TL 追加 + side=NEUTRAL |
| 5 (BUY V字底+1.17000) | PASS | PASS | **FAIL** (rising channel) | 再判定: side=NEUTRAL |
| 6 (NEUTRAL SUPPRESSED) | PASS | **FAIL** (16t HIGH TL欠) | PASS | 再判定: TL 追加 |

**つまり 6 entries 中 5 entries が新 validator では reject される**. これは既存 entries の品質を AI 自己申告で「v7 doctrine 適用」と称していた事の客観評価. 過去の私の主張は実態より良く書かれていた事の証拠.

対応方針 (推奨):
- 既存 entries は corpus に残す (再 add しないので validator は再発火しない)
- 将来 corpus を再生成する時に F15/F16 を満たす spec を構築する
- もしくは: 1 件ずつ手動で再 author し、structure_detector の出力を取り入れて再 add

### 5.11 tests
`tests/corpus/test_entry_validator.py` に 16 件:
- happy path
- F1 (skeleton / too-short / label==key) × 3
- F4 (missing keys) × 1
- F5 (too-tight stop / accepted gap) × 2
- F7 (zone OoR / line endpoint OoR) × 2
- F8 (no slanted / horizontal-only trendline) × 2
- F9 (missing entry / stop / target) × 3
- store integration (rejects / skip_validation works) × 2

---

## 6. 未実装 invariant (推奨 - 優先順)

### 6.1 高優先

#### 6.1.1 stub PNG 検出 (F2 補強)
- builder で `chart_png_path.stat().st_size < 5000` なら raise
- もしくは PNG header の最初 N byte が known stub と一致したら raise

#### 6.1.2 数値整合 (market_story_ja vs spec.lines/points)
- market_story_ja に書かれた数字 (1.17412, 1.17041 等) を抽出
- spec.lines/points の price 集合と subset 関係になっているか確認
- 違反: 「story には 1.17412 と書いてあるのに spec には無い」を catch

#### 6.1.3 snapshot test (chart PNG hash 固定)
- 各 corpus entry の chart を render し SHA256
- `tests/render/test_snapshot.py` で固定値と比較
- renderer 変更時に意図しない PNG 変化を catch

#### 6.1.4 bbox overlap detection (F10 補強)
- matplotlib の `Text.get_window_extent()` で全 annotation の bbox を取得
- 重なり率 > 50% なら raise
- ENTRY ★ と STOP ✕ が pixel level で重なる事例を catch

### 6.2 中優先

#### 6.2.1 pattern 認識の独立検証
- spec が `pattern_label_ja="ダブルトップ"` を主張する時、code が pivot から再判定
- ルール例: 2 つの major HIGH が price 差 < ATR×0.5 なら double top 候補
- AI 主張と code 判定が不一致なら warn

#### 6.2.2 fib level の数値検証
- spec.zones に kind="fibonacci_prime" がある時、price_low/high が起点・終点から計算した 50%/61.8% と ±0.1pip 以内か
- 違反: AI が typo した fib zone を catch

#### 6.2.3 RR 検証
- entry_l, stop_l, target_l がある時、RR = |target-entry| / |stop-entry|
- side=SELL なら entry > target かつ entry < stop が必要
- side=BUY ならその逆
- spec の rr_comment_ja に書かれた RR と code 計算が ±0.1 以内

### 6.3 低優先

#### 6.3.1 candidate enumerator (探索を code に移す)
- `src/fx_monitor/live/tl_enumerator.py`: pivot から N choose 3 で best-fit line top-K
- `src/fx_monitor/live/level_enumerator.py`: HIGH cluster / LOW cluster 検出
- `src/fx_monitor/live/pattern_detector.py`: double top / H&S / triangle のルールベース判定
- AI prompt に top-K 候補を渡し、AI は選ぶだけ

#### 6.3.2 doctrine glossary lint
- result_ja / market_story_ja で使われた用語が glossary 66 用語と一貫しているか
- 例: 「リテスト」と「再テスト」を混在させていないか

#### 6.3.3 HTF/Fundamentals data 一貫性
- step.status=UNKNOWN の場合、missing_or_waiting に何か入っている事
- step.missing_or_waiting に書かれたキーが、knowledge_pack の宣言した data source と整合

---

## 7. AI 行動規範 (in-session)

これは私 (Claude) がこの project で守るべき行動ルール. 違反したら指摘してください.

### 7.1 自然語の主張ルール

**禁止する表現** (= 必ず疑うべき):

| 言ってはいけない | なぜ | 代わりに |
|---|---|---|
| 「verified」「全部見た」 | 2.C.16 の自然 failure mode | 「pytest 172 passed」「6 PNG を Read で開いた」と具体的に |
| 「completed」「完成しました」 | overstate | 「validator まで実装、視覚 verify は未実施」 |
| 「次から気をつけます」 | 2.D.32 (覚えない) | 「validator F-N に追加します」 |
| 「コードよりAIが優れてる」 | 2.C.25 | task ごとに分離 (§4.2) |
| 「私を信用してください」 | 2.C.17 | 「test pass を見てください」 |
| 「真剣にやります」 | 2.A.6 | 「commit/test の差分で示します」 |

### 7.2 「分かりません」を first-class option にする

不確実な時は以下を優先:
- 「分かりません」「データ不足です」「確認します」
- 推測する場合は必ず「推測ですが」「データなしの仮定で」と明示

### 7.3 ユーザー指摘への対応 (F13 防止)

ユーザーが「X が間違ってる」と言ったら:
1. **即否定しない**
2. **該当 data/code を Read or grep で開く**
3. **確認結果を報告**: 「指摘通り X は誤りでした」or「確認しましたが X は (理由で) 正しいと考えます」
4. 即答 = 禁止

### 7.4 capability の宣言 (F12 防止)

ユーザーが action を指示した時、私にできない場合は **最初に** 言う:
- 「過去メッセージの画像を repo に保存できません. ユーザーが commit してください」
- 「outcome の真因を私が確定できません. 推測までになります」
- 「視覚 layout の overlap を信頼できる形で判定できません. snapshot test と人間目視に頼ります」

### 7.5 commit message ルール

- 「verified」を書くのは pytest pass を伴う時だけ
- 「completed」を書くのは tests + validator が pass した task についてだけ
- 不確実な部分は明記: 「partially implemented (snapshot test pending)」等

### 7.6 schema 変更時の checklist

新フィールドを `decision_screen_spec_schema.py` 等に追加したら:
- [ ] grep で全 consumer (renderer, builder, validator, test) を確認
- [ ] consumer を更新 or 「未実装」コメント明示
- [ ] schema field の docstring 追加
- [ ] test を新規 or 更新

### 7.7 silent fallback の禁止

production code の except 節:
- 必ず log + raise (silent fallback NG)
- placeholder return が許される場合は、関数 docstring に「stub fallback to be removed」と明記
- 例外: render の human-friendly degraded mode 等は OK (= ユーザー合意あれば)

### 7.8 数値タイピング自粛 (推奨, 段階移行)

理想:
- price / index / RR を spec field に書く時は code 出力を引用
- AI は narrative (result_ja) で数値を書く時、引用元の field を参照する

短期では完全実装困難なので、validator (§5) が catch する.

### 7.9 約束を file に書く

「今後 X する」と私が言ったら、その瞬間に file (この SPEC.md) に書き足す.
書かない約束 = 次 session で消える = 嘘になる.

---

## 8. Code 不変条件 (現存 + 推奨)

§5 + §6 を formal にまとめたもの. 全部を test に encode するのが目標.

| ID | 不変条件 | 実装場所 | 実装状態 |
|---|---|---|---|
| F1 | result_ja に placeholder なし、len ≥ 15 | entry_validator.py | ✓ |
| F2 | chart_png_path size > 5KB (推奨) | builder | △ 推奨 |
| F3 | trendline は start/end_index 必須なら slanted 描画 | entry_chart.py | ✓ |
| F4 | spec.procedure_steps が knowledge_pack 全 key を含む | entry_validator.py | ✓ |
| F5 | |entry.price - stop.price| >= ATR×0.5 | entry_validator.py | ✓ |
| F6 | F5 と同じ | entry_validator.py | ✓ |
| F7 | index/index_low/high が [0, 120) | entry_validator.py | ✓ |
| F8 | spec.lines に slanted trendline ≥ 1 | entry_validator.py | ✓ |
| F9 | spec.lines に entry/stop/target line 必須 | entry_validator.py | ✓ |
| F10a | label flip when near ylim edge | entry_chart.py | ✓ |
| F10b | bbox overlap detection (推奨) | entry_chart.py | △ 推奨 |
| F11a | 「verified」= pytest 全 pass | §9 規定 | ✓ |
| F15 | 4+ touch TL を AI が見落としてないか | entry_validator.py | ✓ |
| F16 | channel 検出 + side != NEUTRAL なら raise | entry_validator.py | ✓ |
| F11b | snapshot test for chart PNG (推奨) | tests/ | △ 推奨 |
| Numeric coherence | market_story_ja の数字 ⊆ spec.{lines,points,zones}.price (推奨) | entry_validator.py | △ 推奨 |
| Pattern verification | code re-checks pattern_label_ja claim (推奨) | entry_validator.py | △ 推奨 |
| Fib precision | fib zone price_low/high が ±0.1pip 以内 (推奨) | entry_validator.py | △ 推奨 |
| RR coherence | rr_comment_ja の RR と code 計算が一致 (推奨) | entry_validator.py | △ 推奨 |

---

## 9. 検証手順 (operationalization)

### 9.1 「verified」の operational 定義

ユーザーへの報告で「verified」と書ける条件:
1. `python -m pytest` が **全 pass** (現状 172 passed)
2. 該当 corpus entries の `validate_entry()` が **errors=[]**
3. (snapshot test 実装後) snapshot が **一致**

それ以外の状態で「verified」と書くのは嘘.

### 9.2 「completed」の定義

`completed` を task で使えるのは:
- 該当機能の test が pass (新規 test を含む)
- validator rule が新規追加されている (機能が invariant を加えるなら)
- commit が push されている

### 9.3 commit 前 checklist

ユーザーから commit 指示が出た時:
- [ ] `git status` で対象を確認
- [ ] `pytest` を full 実行 → 全 pass
- [ ] `git diff --cached` で内容確認
- [ ] commit message に overstate なし
- [ ] push 後、URL/SHA を報告

### 9.4 chart 視覚確認 (人間目視)

私 (AI) は信頼できる視覚判定を持たない. 必ず人間目視で:
- ENTRY ★ / STOP ✕ / TARGET ◆ marker が pixel 重ならず分離して見えるか
- 斜め TL が斜めに描画されているか (水平に潰れてないか)
- 火薬庫 / フィボ プライムゾーン 等の zone が適切な範囲に塗られているか
- pattern banner が title と被ってないか
- pivot label が chart 枠外に出てないか

---

## 10. ロードマップ

### フェーズ 1: validator 拡充 (現在進行)
- [x] F1-F9 の validator 実装 (commit `7d31385`)
- [x] silent fallback 削除 (F2)
- [x] 既存 6 entries が validator pass
- [x] tests 172 passed (16 新規)

### フェーズ 2: 数値整合 invariant 追加
- [ ] F2 補強: PNG size check (5KB)
- [ ] Numeric coherence: market_story_ja vs spec.{lines,points,zones} の price 一致
- [ ] Fib precision: fib zone と起点/終点 計算の一致
- [ ] RR coherence: rr_comment_ja と code 計算の一致

### フェーズ 3: 視覚 invariant
- [ ] Snapshot test: 6 entries の chart PNG SHA256 固定
- [ ] bbox overlap detection: matplotlib annotation 重なり判定
- [ ] CI で snapshot test を run

### フェーズ 4: 探索の code 化
- [ ] TL enumerator: pivot から best-fit line 候補 top-K
- [ ] Level enumerator: HIGH/LOW cluster 検出
- [ ] Pattern detector: double top / H&S / triangle ルールベース
- [ ] live AI prompt が候補 top-K を含むよう改修
- [ ] AI は選ぶだけ (採用/却下 + reason_ja)

### フェーズ 5: corpus 拡張
- [ ] candidate_filter で 100+ anchor を抽出
- [ ] live mode で AI 判定を蓄積
- [ ] retrieval (CLIP + numeric) を活用した learning

### フェーズ 6: 実用化
- [ ] yfinance live feed 接続 (既存)
- [ ] Forex Factory calendar 自動更新 (既存)
- [ ] 観測ログ → 月次自己診断レポート (既存 `monthly_report.py`)

---

## 付録 A: file 一覧

### 重要 source
- `src/fx_monitor/ai/knowledge_pack_v2.json` — doctrine v7 の ground truth
- `src/fx_monitor/corpus/entry_validator.py` — F1-F9 validator
- `src/fx_monitor/corpus/store.py` — `add()` で validator 起動
- `src/fx_monitor/render/entry_chart.py` — chart 描画 (zones, slanted TL, markers, label flip)
- `src/fx_monitor/ai/decision_screen_spec_schema.py` — spec の pydantic schema
- `src/fx_monitor/live/market_pack_v2.py` — pack の build
- `src/fx_monitor/tools/check_prepare.py` / `check_finalise.py` — live 1判定
- `src/fx_monitor/tools/dashboard.py` — corpus → static HTML
- `src/fx_monitor/tools/dump_doctrine.py` — knowledge_pack → markdown

### 重要 docs
- `docs/SPEC.md` — この文書
- `docs/doctrine_v7.md` — doctrine の人間可読版
- `docs/live_dashboard/index.html` — 6 entries の閲覧 UI
- `data/corpus/default/entries.jsonl` — 6 entries の生 data
- `data/corpus_pngs/<id>.png` — chart 画像

### 重要 test
- `tests/corpus/test_entry_validator.py` — 16 件 validator test
- `tests/corpus/test_store.py` — store mechanics
- `tests/render/` — renderer test (snapshot 未実装)
- `tests/tools/test_check_flow.py` — live tool e2e

---

## 付録 B: 用語集 (project 独自)

- **王道 (おうどう)**: 高勝率なテクニカル設計図. doctrine v7 が定義.
- **HTF supremacy**: 上位足の絶対的優位性原則
- **fundamentals supremacy**: ファンダメンタルの絶対的優位性原則
- **Triple Confluence**: フィボゾーン × 反転パターン × レジサポ転換 の3軸交点
- **Build-up**: ブレイク前のエネルギー蓄積期間
- **火薬庫**: stop loss 注文集積帯 (上方/下方)
- **intervention 2-stage trap**: 為替介入の2段構え狩り (養分パターン)
- **anchor**: corpus entry の判定時点 (window の右端)
- **window**: 60 本の M5 candle = 5時間
- **pip**: 0.0001 (EUR/USD)
- **ATR**: Average True Range, ボラティリティ指標
- **F1...F13**: §3 の失敗識別子
- **layer / 層**: §4.1 のデータ→AI→render→validator の段階

---

## 付録 C: 改訂履歴

- v1 (2026-05-04): 初版. commit `7d31385` 時点で確定. 35 弱点 / 13 失敗 / 9 既存 invariant / 7 推奨 invariant をカバー.
- v1.1 (2026-05-04, commit次): F14/F15/F16 追加. `structure_detector.py` 実装で TL/channel/pattern 検出を code 側に移行. validator F15/F16 で AI の探索漏れと channel 内 directional 判定を機械検出. 既存 6 entries 中 5 entries が新 validator では reject される事実を §5.10 に明記.

---

## 末尾の宣言 (私から)

この文書を書いた時点での私 (Claude session) の commitment:

1. この SPEC.md を **削除/簡略化しない**. ユーザー指示なしの変更不可.
2. 将来の commit message は §7.5 のルールに従う.
3. 「verified」「completed」を §9 の operational 定義以外で使わない.
4. ユーザー指摘 → 必ず Read/grep で確認してから返答 (§7.3).
5. capability gap (§7.4) を最初に宣言する.

これらは私の session 内の宣言. 次 session の Claude には引き継がれない. 引き継ぐには **このファイルを次 session の Claude に Read させる** のがユーザーの責任.

(もし将来の Claude がこの文書を Read してこの行に到達したなら: §7 を最初に守ってください. 過去の私と同じ失敗を繰り返さないため.)
