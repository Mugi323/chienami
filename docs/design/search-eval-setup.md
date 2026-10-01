# 検索評価ツール（Recall@k / MRR）の使い方（Issue #38）

`app/eval/` に追加した評価ツール。chienami-api（Issue #34）へ質問を投げ、正解として
指定したOutline文書URLが検索結果の何位に現れたかからRecall@k・MRRを計測する。

design書11章の方針どおり、評価は「LLMの文章の上手さ」ではなく「必要な根拠文書を
取得できたか」で行う。

## 実際の質問セットはまだ存在しない

**本Issueの時点で、研究室の実文書がOutlineに投入されておらず、意味のある20〜50問の
質問セットを作れる状態ではない。** そのため本Issueで用意したのは評価の「ツールと形式」
のみであり、実際の質問セット作成は研究室メンバーによる今後のタスクとする。

## 1. 質問セットの作成

1. `app/eval/questions.example.yaml` を `app/eval/questions.yaml` としてコピーする。
2. 研究室の実際のOutline文書をもとに、20〜50問程度の「正解が分かっている質問」に
   差し替える。`expected_urls` には、その質問に対する正しい根拠文書のURL
   （`https://knowledge.lab.local/doc/...`、chienami-indexerがQdrantへ格納するものと
   同じ形式）を1つ以上指定する。
3. `questions.yaml` は `.gitignore` 対象ではない。研究室として質問セットを蓄積・
   バージョン管理したい場合はそのままコミットしてよい（実際の文書URLを含むため、
   外部公開リポジトリではない前提での判断）。

## 2. 実行

```bash
docker compose run --rm eval
```

既定では `app/eval/questions.yaml` を読み込み、`http://api:8000` へ問い合わせて
Recall@1/3/5/10とMRRを標準出力へレポートする。

パラメータを変更する場合:

```bash
docker compose run --rm eval /app/questions.yaml --k 1,5,10
```

## 3. 結果の見方

```
評価対象: 25問
  [HIT ] rank=1  FlashAttentionを使うと学習が落ちる場合の対処法は？
  [MISS] rank=-  ...

Recall@1: 0.600
Recall@3: 0.760
Recall@5: 0.840
Recall@10: 0.880
MRR: 0.712
```

- `Recall@k`: 正解文書が上位k件以内に含まれた質問の割合。
- `MRR`: 正解文書が現れた順位の逆数の平均（上位に出るほど1に近づく）。

## 4. ハイブリッド検索との比較・RAG回答の評価（Phase 4）

```bash
docker compose run --rm eval /app/questions.yaml --mode semantic,hybrid --rag
```

- `--mode`: カンマ区切りで検索方式を指定する（`semantic` / `hybrid`、既定は `semantic`）。複数指定すると、
  方式ごとのレポートの後に比較表を出す
- `--rag`: 全質問を `POST /chat` に投げ、RAG回答を評価する（LLMの生成を待つため時間がかかる）

### 答えのない質問

`expected_urls: []` の質問は「知識ベースに答えがない質問」として扱う。検索のRecall/MRRの計算からは除き、
`--rag` では回答を控えたか（`abstained`）を評価する。「根拠がなければ回答を控える」動作の確認と、
`RAG_MIN_RERANK_SCORE` の調整に使うため、質問セットには答えのない質問も数問入れておく。

### 出力例

```
[検索方式の比較]
指標            semantic    hybrid
Recall@1         0.600     0.720
Recall@3         0.760     0.840
Recall@5         0.840     0.880
Recall@10        0.880     0.920
MRR              0.712     0.790

[RAG回答] 評価対象: 28問
  [引用OK] 3.2s  FlashAttentionを使うと学習が落ちる場合の対処法は？
  [未引用] 2.8s  ...
  [根拠MISS] 2.5s  ...
  [控えた] 0.4s  明日の研究室の天気は？
  ...

答えのある質問: 25問
  回答した割合:           0.920
  正解文書が根拠に入った: 0.880
  正解文書を引用した:     0.800
答えのない質問: 3問
  回答を控えた割合:       1.000
平均回答時間: 2.9秒
```

各質問のラベルの意味は次のとおり。

| ラベル | 意味 |
| --- | --- |
| `引用OK` | 正解文書を根拠にし、回答で引用した |
| `未引用` | 正解文書は根拠に入ったが、回答では引用しなかった |
| `根拠MISS` | 正解文書が根拠に入らなかった（検索・Rerank・しきい値の問題） |
| `控えた` | 回答を控えた。答えのある質問なら取りこぼし、答えのない質問なら正しい動作 |
| `回答した!` | 答えのない質問なのに回答した（誤答・幻覚のおそれ） |

### `RAG_MIN_RERANK_SCORE` の調整の目安

- 答えのある質問で `控えた` が多い → しきい値を下げる
- 答えのない質問で `回答した!` が出る → しきい値を上げる

Chunking設定（`INDEXER_CHUNK_SIZE` / `INDEXER_CHUNK_OVERLAP`、[indexer-setup.md](indexer-setup.md)参照）
を変えて再索引化・再評価し、スコアの変化を比較する運用を想定している（design書5.3節）。

## 既知の制約

- Phase 4の比較・RAG評価（4節）も、ユニットテスト（API呼び出しはrespxでモック）のみ実施済み。
  実際の計測はGPU機で行う。
- 本Issueの時点で実際のchienami-apiに対するend-to-end実行は未実施（開発環境にDockerが無く、
  評価対象の実文書も無いため）。ユニットテスト（`pytest`、API呼び出しはrespxでモック）
  のみ実施済み。
- 正解判定はURLの完全一致。将来、部分一致や複数正解の重み付けなど評価方法を拡張する
  余地がある。
