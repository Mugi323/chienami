# chienami-indexer の設定・動作確認（Issue #32）

`app/indexer/` に追加したPythonサービス。Outlineの「全員閲覧可Collection」内の公開済み文書を
定期的にEmbeddingし、Qdrant（Issue #30）へ格納する。

## 1. Outline APIキーの発行

1. `https://knowledge.lab.local` へ管理者アカウントでログインする。
2. `Settings → API & Apps` を開き、新しいAPIキーを発行する（名前は `chienami-indexer` 等、
   識別しやすいものにする）。
3. 発行されたキーを `config/docker.env` の `OUTLINE_API_TOKEN` に設定する。
   **APIキーはOutlineの全データへアクセスできるため、パスワードと同様に扱うこと。**
4. `docker compose up -d --force-recreate indexer` で反映する。

`docker.env` は `.gitignore` 対象のため、この値がGit管理下に入ることはない。

## 2. Collectionの公開設定について

indexerは、CollectionのデフォルトアクセスがOFFではない（`permission` が
`read`/`read_write` の）Collectionのみを索引対象にする。Outlineの
Collection設定画面で「ワークスペースの全員がアクセス可能」になっているCollectionが対象。
招待制・グループ限定のCollectionは索引化されない（design書7.3節、権限フィルタ未完成のため）。

## 3. 動作確認

```bash
docker compose logs -f indexer
```

初回サイクルで対象Collection数・索引更新した文書のログが出力される
（`索引対象Collection数: N`、`索引更新: document_id=... title=... chunks=N`）。

Qdrant側にデータが入ったことを確認する場合は
[search-infra-setup.md](search-infra-setup.md) の手順でQdrantのcollectionsエンドポイントを
確認するか、以下でpoint数を確認する。

```bash
docker compose run --rm --no-deps --entrypoint sh outline -c \
  "wget -qO- --header='api-key: <QDRANT_API_KEYの値>' \
   http://qdrant:6333/collections/chienami_documents"
```

`points_count` が0より大きければ索引化されている。

## 4. パラメータ調整

`config/docker.env` で以下を調整できる。

- `INDEXER_INTERVAL_SECONDS`: 索引化サイクルの間隔（秒）。既定600秒。
- `INDEXER_CHUNK_SIZE` / `INDEXER_CHUNK_OVERLAP`: Chunkingの目標文字数・オーバーラップ。
  初期値であり、検索評価（Recall@k、design書11章）の結果に応じて調整する前提。

## 既知の制約

- 差分判定は文書全体のcontent_hashのみで行う。1段落だけの変更でも文書全体を再Chunking・
  再Embeddingする（文書単位より細かい差分検出は未実装）。
- 索引化は全文書を毎サイクル走査する（Outline側の更新イベントを購読するWebhook方式ではない）。
  文書数が非常に多い場合はサイクル時間が伸びる可能性がある。
- 本Issueの時点で実際のOutlineインスタンス・Qdrant・Embeddingサービスに対する
  end-to-endの起動確認は未実施（開発環境にDockerが無いため）。ユニットテスト
  （`pytest`、Outline API/Embedding APIはモック）のみ実施済み。実サーバでの動作確認が別途必要。
