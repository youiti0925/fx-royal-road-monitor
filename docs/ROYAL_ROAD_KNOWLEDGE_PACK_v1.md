# Royal Road Knowledge Pack v1

> このドキュメントは AI レビューに **毎回そのまま渡す** 知識パック。
> AI は一般知識ではなく、ここに書いてあることだけを判断材料にしてよい。

---

## 1. 王道手順 (royal road) とは

短期スキャルや裁量の偶発性に依存せず、**環境認識 → セットアップ確認 → 引き金 → 管理** の
順番で必ずチェックを通す手続き。途中の段が満たされない場合、後段に進んではならない。

### 1.1 順序 (固定)

1. **環境認識 (HTF context)**
   - 上位足 (H4 / D1) のトレンド方向。
   - 直近の意味のあるスイング高安。
   - 重要 S/R / ラウンドナンバー。
2. **セットアップ (LTF structure)**
   - 上位足方向と整合する押し目 / 戻りの構造。
   - HH/HL (上昇) または LH/LL (下降) の連続性。
   - キーレベルでの反応 (反発の足、ピンバー、包み足など)。
3. **引き金 (trigger)**
   - 直近スイングのブレイク / リテスト。
   - 出来高 / モメンタム指標の追認 (ある場合)。
4. **管理 (management)**
   - 損切り位置: 直近スイングの外側、ATR 1.0–1.5x が目安。
   - リワード: 直近反対側スイングまで、最低 1R 以上の余地。

### 1.2 王道から外れる典型パターン (避ける)

- 上位足と逆方向の "綺麗に見える" 押し戻し。
- レンジ中央でのブレイク追随 (ノイズ域)。
- 重要指標発表の直前 / 直後 (定義: ±15 分)。
- 流動性が薄い時間帯のブレイク (アジア早朝など、対象通貨ペアによる)。

---

## 2. 判定基準: PASS / WAIT / WARN / BLOCK / UNKNOWN

各レビュー出力は必ず以下のいずれか **1 つだけ** を `verdict` として返す。

| verdict   | 意味                                                                                                |
| --------- | --------------------------------------------------------------------------------------------------- |
| `PASS`    | 王道手順をすべて満たす。READY を出してよい候補。                                                     |
| `WAIT`    | 大筋は王道だが、引き金 (trigger) がまだ発生していない。観察継続。                                    |
| `WARN`    | 王道のどれかに弱点 / 不整合あり。READY にしてはいけないが、注視はしてよい。                          |
| `BLOCK`   | 王道に明確に反する (上位足逆行、指標直前、レンジ中央など)。READY にしてはいけない。                  |
| `UNKNOWN` | 与えられた payload / 画像から判断するのに情報が不足。READY にしてはいけない。                        |

### 2.1 READY を出してよい条件

すべて成立しなければならない:

- ルールエンジンの判定が `PASS` である。
- OpenAI レビューと Claude レビューの **両方** が `PASS`。
- いずれの reviewer も `disagreements` (重大な不整合) を上げていない。
- 直近 `NOTIFY_COOLDOWN_SECONDS` 以内に同一 symbol/timeframe で `READY` を出していない。

### 2.2 READY を出してはいけない条件 (どれか 1 つでも該当したら不可)

- ルールエンジンが `WAIT` / `WARN` / `BLOCK` / `UNKNOWN`。
- 二人の reviewer のどちらか一方でも `PASS` 以外。
- 二人の reviewer の verdict が一致しない。
- 二人の reviewer の方向 (`bias`: long/short/none) が一致しない。
- 重要指標 ±15 分。
- payload に欠損 (例: HTF データなし、ATR 不明)。

---

## 3. payload (AI に渡す構造化情報) の最小要件

```
{
  "symbol": "USDJPY",
  "timeframe": "M5",
  "timestamp_utc": "2026-05-03T13:55:00Z",
  "htf": {
    "h4_trend": "up|down|range",
    "d1_trend": "up|down|range",
    "key_levels": [155.20, 154.80]
  },
  "ltf": {
    "structure": "HH-HL|LH-LL|range|broken",
    "last_swing_high": 155.10,
    "last_swing_low":  154.90,
    "atr_14":          0.12
  },
  "trigger": {
    "type":     "breakout|retest|pinbar|engulf|none",
    "occurred": false
  },
  "calendar": {
    "high_impact_within_15min": false
  }
}
```

これが揃っていない場合、AI は `UNKNOWN` を返さねばならない。
推測で埋めない。

---

## 4. 出力 JSON schema (要点)

詳細フィールド定義は `src/fx_monitor/ai/schema.py` を **真の参照元** とする。

```
{
  "verdict":  "PASS|WAIT|WARN|BLOCK|UNKNOWN",
  "bias":     "long|short|none",
  "confidence": 0.0,                       // 0.0–1.0
  "reasons": ["..."],                      // 王道のどの段に基づくか
  "disagreements": ["..."],                // payload と矛盾する点があれば
  "missing":  ["..."],                     // payload で欠けていたフィールド
  "suggested_invalidation": 154.85,        // 任意。bias と整合する損切り候補。
  "suggested_target":       155.40         // 任意。
}
```

reviewer は **この schema を破ってはならない**。

---

## 5. 二重レビュー比較 (compare)

OpenAI と Claude の出力を比較し、以下のうち 1 つを返す:

- `AGREE_PASS`   : 両者 PASS かつ bias 一致 → READY 候補
- `AGREE_HOLD`   : 両者 PASS 以外で一致 (例: 両者 WAIT)
- `DISAGREE`     : 一致しない
- `INSUFFICIENT` : どちらかが UNKNOWN

`AGREE_PASS` 以外では READY を発行しない。

---

## 6. 通知の落とし所

- `READY`        : ルール PASS + AGREE_PASS のとき。Discord/LINE に push、コンソールにも。
- `WATCH`        : ルール PASS + AGREE_HOLD など、注視レベル。コンソールのみ (or 静かなチャネル)。
- `SUPPRESSED`   : DISAGREE / BLOCK / 指標直前 / cooldown 中 → 通知しない (ログのみ)。

詳細は `docs/NOTIFICATION_POLICY.md`。
