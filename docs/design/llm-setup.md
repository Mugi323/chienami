# LLM基盤（llama.cpp）の動作確認（Issue #48）

`app/compose.yaml` に追加した `llm` サービス。llama.cppでQwen3-8B（GGUF, Q4_K_M量子化）を
OpenAI互換APIとして配信する。開発機・本番サーバともにNVIDIA GPU搭載であることを確認済みのため、
CUDA版イメージ・フルGPUオフロード構成を採用している。

## 前提

- `docker compose up -d` で `llm` サービスが起動していること。
- ホストにNVIDIA GPU・ドライバ・`nvidia-container-toolkit`が導入済みで、
  `docker info` の `Runtimes` に `nvidia` が含まれていること。

## 1. 起動確認

```bash
docker compose ps llm
docker compose logs llm
```

初回起動時はモデル（約4.7GB）のダウンロードが発生し、`healthy` になるまで数分かかる
（実機で確認: 回線速度依存。ヘルスチェックの `start_period` はこれを考慮した値にしてある）。

## 2. 動作確認（OpenAI互換API）

APIキーは `config/docker.env` の `LLAMA_API_KEY`（`setup.sh` が自動生成）。

```bash
docker compose run --rm --no-deps --entrypoint sh api -c \
  "wget -qO- --header='Authorization: Bearer <LLAMA_API_KEYの値>' \
   --header='Content-Type: application/json' \
   --post-data='{\"messages\":[{\"role\":\"user\",\"content\":\"こんにちは\"}],\"max_tokens\":200}' \
   http://llm:80/v1/chat/completions"
```

日本語で応答が返ることを確認する。

## 3. VRAM使用量

実機（RTX 3060, 12GB VRAM）で `embedding` サービスと同時稼働させ、`nvidia-smi` で
合計使用量が12GB以内に収まることを確認済み（実測: 約8GB）。Reranker（別Issue）を
追加する際は、追加分のVRAM使用量にも注意すること。

```bash
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

## 既知の制約・注意点

- Qwen3-8Bは既定で拡張思考（reasoning）モードを使う。レスポンスの `content` が空で
  `reasoning_content` にのみ内容が入り、`max_tokens` を使い切って `finish_reason: "length"`
  になることがある（実機で確認）。RAGエンドポイント（Phase 4、別Issue）実装時は、
  thinkingモードの無効化またはmax_tokensを十分大きく取る対応が必要。
- GPU未搭載環境ではこのサービスは動作しない。design書4.5節の通りPhase 1〜3ではLLMは
  必須ではないため、GPU非搭載サーバでは `llm` サービスを起動しない運用も可能
  （`docker compose up -d` から `llm` を除外する、または `docker compose stop llm`）。
- モデル選定は固定ではない（design書4.5節）。`--hf-repo` / `--hf-file` を変更すれば
  別モデルに切り替えられる。
