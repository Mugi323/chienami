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

- Embeddingモデル（Qwen3-Embedding-0.6B）はCPU版イメージで動作する。GPU未搭載サーバでも動作するが、
  大量文書の一括Embedding時は速度が遅くなる可能性がある（design書9節）。
- `embedding` サービスの起動オプション（`--max-batch-tokens` / `--tokenization-workers`）は、
  割当メモリが少ない環境（実機検証: WSL2 + Docker Desktop、7.7GB）でウォームアップ時に
  クラッシュしないよう既定値より絞ってある（Issue #42）。メモリに余裕のあるサーバではより
  大きい値に緩めてスループットを上げられる可能性がある。
