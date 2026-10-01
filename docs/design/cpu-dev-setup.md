# GPU非搭載の開発機での起動（Issue #55）

`app/compose.yaml` は本番サーバ（NVIDIA GPU搭載）向けの構成で、`embedding` / `llm` がGPUを前提にしている。
GPUのない開発機では、CPU用のoverride `app/compose.cpu.yaml` を重ねて起動する。

目的は**Phase 3/4の結合動作確認**。回答品質・速度・VRAM使用量の評価はGPU機で行う。

> **RAM 16GB以上の機械向け。** RAM 8GB程度の機械（実機: WSL2 + Docker Desktop、7.7GB）では、
> Outline・Authentikと一緒にAI系（embedding / reranker / llm）を動かすと、スワップを使い切って
> Docker Desktopごと応答しなくなった。そうした機械では、モデルのコンテナは起動しない。
> 開発は各サービスの単体テスト（pytest。外部サービスはモック）で行い、実際のモデルでの確認はGPU機でまとめて行う。

## 差し替える内容

| サービス | 本番（compose.yaml） | CPU開発（compose.cpu.yaml） |
| --- | --- | --- |
| `embedding` | TEI `cuda-1.8` | TEI `cpu-1.9`。`--max-batch-tokens 2048` / `--tokenization-workers 2` を付ける |
| `llm` | llama.cpp `server-cuda` + Qwen3-8B Q4_K_M | llama.cpp `server` + Qwen3-1.7B Q8_0（`--ctx-size 4096`） |
| `reranker` | llama.cpp `server-cuda` + Qwen3-Reranker-0.6B Q8_0 | llama.cpp `server`（`--n-gpu-layers 0`） |

どちらもGPUの予約（`deploy.resources`）を外している。

`embedding` のオプションはIssue #42で確認した対策。既定値（16384トークン）のままだと、割当メモリ7.7GB程度の
環境ではウォームアップ時にメモリ不足でクラッシュし、再起動を繰り返す。

## 起動・停止

`app/scripts/` のスクリプトは、環境変数 `CHIENAMI_CPU=1` を付けるとoverrideを自動で重ねる。

```bash
CHIENAMI_CPU=1 ./app/scripts/start.sh
CHIENAMI_CPU=1 ./app/scripts/stop.sh
```

docker composeを直接使う場合:

```bash
cd app
docker compose -f compose.yaml -f compose.cpu.yaml up -d
```

`CHIENAMI_CPU` を付けない場合は、従来どおりGPU構成で起動する。

## メモリが足りない場合（AI系だけ起動する）

RAM 8GB程度の機械では、Outline・Authentik・AI系をすべて同時に動かすと厳しいことがある。
検索/RAGの開発だけなら、必要なサービスだけを起動する。

```bash
cd app
docker compose -f compose.yaml -f compose.cpu.yaml up -d qdrant embedding reranker llm api
```

索引化（indexer）にはOutlineが必要なので、索引を作るときだけ `outline` / `postgres` / `redis` も起動する。

## 動作確認

```bash
cd app
docker run --rm --network app_default curlimages/curl -s -X POST http://embedding:80/embed \
  -H 'Content-Type: application/json' -d '{"inputs":["テスト"]}'

docker run --rm --network app_default curlimages/curl -s -X POST http://llm:80/v1/chat/completions \
  -H "Authorization: Bearer <LLAMA_API_KEYの値>" -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"日本の首都は？"}],"max_tokens":64,
       "chat_template_kwargs":{"enable_thinking":false}}'
```

実機の結果（WSL2、RAM 7.7GB、GPUなし）:
- `embedding` / `llm`: どちらも応答した。`llm` の応答時間は短い質問で約5秒
- `reranker`: 候補4件の短い文では正しく並べ替えられた。ただし候補20件（各約550字）では約177秒かかった。
  さらに他のAI系と同時に動かすとメモリが枯渇したため、この機械でrerankを動かすのは現実的ではない

## 注意

- Phase 1の頃に作った `config/docker.env` には、Phase 3/4用のキー（`QDRANT_*` / `EMBEDDING_URL` / `LLAMA_API_KEY` など）が
  ない。`setup.sh` は既存ファイルを変更しないので、`docker.env.example` を見て足りないキーを手動で追記する。
- 初回起動時はモデルのダウンロードが入る（Embedding 約1.2GB、LLM 約1.8GB）。
