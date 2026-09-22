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

## 既知の制約

- 本Issueの時点で実際のQdrant/Embeddingサービスに対するend-to-endの起動確認は未実施
  （開発環境にDockerが無いため）。ユニットテスト（`pytest`、依存サービスはモック）のみ
  実施済み。実サーバでの動作確認が別途必要。
- 検索結果の並び順はベクトル類似度スコアのみに基づく。Keyword Search・Reranker・権限フィルタ
  （制限付きCollectionへの対応）はPhase 4以降の対象（design書12章）。
