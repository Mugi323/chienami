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

Chunking設定（`INDEXER_CHUNK_SIZE` / `INDEXER_CHUNK_OVERLAP`、[indexer-setup.md](indexer-setup.md)参照）
を変えて再索引化・再評価し、スコアの変化を比較する運用を想定している（design書5.3節）。

## 既知の制約

- 本Issueの時点で実際のchienami-apiに対するend-to-end実行は未実施（開発環境にDockerが無く、
  評価対象の実文書も無いため）。ユニットテスト（`pytest`、API呼び出しはrespxでモック）
  のみ実施済み。
- 正解判定はURLの完全一致。将来、部分一致や複数正解の重み付けなど評価方法を拡張する
  余地がある。
