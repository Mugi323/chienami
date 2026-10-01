# chienami-api の動作確認（Issue #34）

`app/api/` に追加したFastAPIサービス。クエリをEmbeddingし、Qdrant（Issue #30/#32）から
検索結果を返す。ブラウザ向けUI・Reverse Proxyでの公開はIssue #4（検索UI）で行うため、
現時点ではDocker内部ネットワークからのみ到達できる。

## 前提

- `docker compose up -d` 済みで、`indexer` によってQdrantに何らかの文書が索引化済みであること
  （[indexer-setup.md](indexer-setup.md)参照）。

## 1. コンテナの起動確認

```bash
docker compose ps api
```

`healthy` になっていることを確認する。

## 2. ヘルスチェック

```bash
docker compose run --rm --no-deps --entrypoint sh outline -c \
  "wget -qO- http://api:8000/healthz"
```

`{"ok":true}` が返れば正常。

## 3. 検索の動作確認

```bash
docker compose run --rm --no-deps --entrypoint sh outline -c \
  "wget -qO- 'http://api:8000/search?q=検索したいキーワード&limit=5'"
```

スコア降順で、`document_id` / `title` / `url` / `score` / `snippet` を含む結果が返る。
`url` はOutlineの当該文書へ直接アクセスできるURL（`https://knowledge.lab.local/doc/...`）。

同一文書から複数チャンクがヒットした場合でも、結果には各文書が最大1回しか出現しない
（最もスコアの高いチャンクが採用される）。

## 4. ハイブリッド検索（Phase 4）

`mode=hybrid` を付けると、Dense検索とKeyword検索を統合し、Rerankerで並べ替える。
`mode` を省略した場合は従来どおり `semantic`（Dense検索のみ）。

```bash
docker compose run --rm --no-deps --entrypoint sh outline -c \
  "wget -qO- 'http://api:8000/search?q=PCRのアニーリング温度&limit=5&mode=hybrid'"
```

処理の流れ（`app/api/chienami_api/search.py` の `SearchService.hybrid_chunks`）:

1. **Dense**: クエリのEmbeddingでQdrantを検索し、上位 `API_HYBRID_CANDIDATES` 件（既定20）のチャンクを取る
2. **Keyword**: クエリから漢字・カタカナ・英数字の連続を抜き出し（ひらがなは除く。最大8語）、
   いずれかを含むチャンクをQdrantの全文インデックス（`text`、multilingual tokenizer）で探す。
   含むキーワードの種類数が多い順に、上位 `API_HYBRID_CANDIDATES` 件を取る
3. **統合**: 2つの順位をRRF（Reciprocal Rank Fusion, k=60）で統合する
4. **Rerank**: 統合後の上位 `API_HYBRID_CANDIDATES` 件をReranker（[reranker-setup.md](reranker-setup.md)）で並べ替える。
   `score` は関連度（0〜1）になる
5. 文書単位で重複を除き、`limit` 件を返す

Rerankerが停止している・エラーになった場合は、ログに記録したうえでRRF順の結果を返す（検索自体は止めない）。

Keyword検索はSemantic Searchと同じQdrant索引を使うため、検索対象（全員閲覧可Collectionのみ）は
Semantic Searchと同じ。全文インデックスはindexerが起動時に作成する（既存のcollectionにも追加される）。

## 既知の制約

- 本Issueの時点で実際のQdrant/Embeddingサービスに対するend-to-endの起動確認は未実施
  （開発環境にDockerが無いため）。ユニットテスト（`pytest`、依存サービスはモック）のみ
  実施済み。実サーバでの動作確認が別途必要。
- `mode=semantic` の並び順はベクトル類似度スコアのみに基づく。Keyword Search・Rerankerは
  `mode=hybrid` で利用できる。権限フィルタ（制限付きCollectionへの対応）は未対応（design書12章）。
- `mode=hybrid` は、ユニットテスト（依存サービスはモック）のみ実施済み。実際のQdrant・Rerankerでの
  確認はGPU機で行う（[reranker-setup.md](reranker-setup.md) 3節）。
