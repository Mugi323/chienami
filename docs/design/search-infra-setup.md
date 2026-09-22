# Phase 3検索基盤（Qdrant / Embedding）の動作確認（Issue #30）

`app/compose.yaml` に追加した `qdrant` / `embedding` サービスの動作確認手順。
両サービスともDocker内部ネットワークに閉じており、ホストへポートをpublishしていないため、
確認は `docker compose exec` 等でコンテナ内部から行う。

## 前提

`./app/scripts/start.sh` 等で `docker compose up -d` 済みであること。

## 1. コンテナの起動確認

```bash
docker compose ps qdrant embedding
```

両方とも `healthy` になっていることを確認する（`embedding` はモデルダウンロードのため
初回起動時は数分かかる場合がある。`start_period: 180s` を超えても `unhealthy` の場合は
`docker compose logs embedding` でダウンロード状況を確認する）。

## 2. Qdrantの疎通確認（APIキー必須）

`config/docker.env` の `QDRANT_API_KEY` の値を控えたうえで、別のコンテナから確認する
（`outline` コンテナ等、curlが無い場合は一時的に `curlimages/curl` を使う）。

```bash
# APIキー無し → 401等で拒否されることを確認
docker compose run --rm --no-deps --entrypoint sh outline -c \
  "wget -qO- http://qdrant:6333/collections || true"

# APIキー付き → 200 OKでコレクション一覧が返ることを確認
docker compose run --rm --no-deps --entrypoint sh outline -c \
  "wget -qO- --header='api-key: <QDRANT_API_KEYの値>' http://qdrant:6333/collections"
```

## 3. Embeddingサービスの疎通確認

```bash
docker compose run --rm --no-deps --entrypoint sh outline -c \
  "wget -qO- --header='Content-Type: application/json' \
   --post-data='{\"inputs\":\"動作確認用のテキストです\"}' \
   http://embedding:80/embed"
```

1024次元の数値配列（ベクトル）が返ってくれば正常。

## 既知の制約

- Embeddingサービス（Qwen3-Embedding-0.6B）はNVIDIA GPU（CUDA）版イメージで動作する
  （開発機・本番サーバともにGPU搭載であることを確認済み、Issue #46）。GPU未搭載環境では
  `cuda-1.9` の代わりに `cpu-1.9` イメージ・`deploy.resources.reservations` の削除で
  CPU動作に切り替えられる。CPU動作時はウォームアップ時のメモリ不足に注意
  （Issue #42、`--max-batch-tokens` を絞る対処が必要だった）。
- GPU版イメージは初回起動時にCUDAカーネルのコンパイルが走り、`healthy` になるまで数分
  かかることがある（実機で確認: CPU使用率100%、GPU使用率は低いまま）。ヘルスチェックの
  `start_period` はこれを考慮した値にしてある。
