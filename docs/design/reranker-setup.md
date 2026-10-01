# Reranker基盤（llama.cpp + Qwen3-Reranker-0.6B）の動作確認（Issue #50）

`app/compose.yaml` に追加した `reranker` サービス。検索候補を、クエリとの関連度で並べ替える
cross-encoder。Phase 4のハイブリッド検索/RAGで、LLMに渡す根拠を選ぶときに使う。

## 構成

- イメージ: `ghcr.io/ggml-org/llama.cpp:server-cuda`（`--reranking` モード）
- モデル: `ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF`（ggml-org公式のGGUF変換版。元モデルはApache-2.0）
- エンドポイント: `POST http://reranker:80/v1/rerank`（Docker内部ネットワークのみ。APIキーなし）

### TEIを使わなかった理由

Issueの当初案はTEI（Embeddingと同じ仕組み）だった。しかしTEI 1.9では、次の2つとも起動できなかった（実機で確認）。

- `Qwen/Qwen3-Reranker-0.6B`: CausalLM型のため、pooling設定が見つからずエラーになる
- seq-cls変換版（`tomaarsen/Qwen3-Reranker-0.6B-seq-cls`）: `classifier model type is not supported for Qwen3` で起動できない

llama.cppはQwen3-Rerankerの `--reranking` に対応しており、LLMサービスと同じイメージで運用できるため、こちらを採用した。

## 1. 起動確認

```bash
cd app
docker compose up -d reranker
docker compose ps reranker      # healthy になること
docker compose logs reranker    # "listening on http://0.0.0.0:80" が出ること
```

初回起動時は、モデル（約640MB）のダウンロードが入る。

## 2. 動作確認

```bash
docker run --rm --network app_default curlimages/curl -s -X POST http://reranker:80/v1/rerank \
  -H 'Content-Type: application/json' \
  -d '{"query":"PCRがうまく増幅しないときの対処",
       "documents":["アニーリング温度を下げる、プライマー設計を見直す、Mg濃度を調整する。",
                    "研究室の忘年会は12月に行います。",
                    "遠心機のローターは使用後に洗浄すること。",
                    "PCR産物が出ない場合、テンプレートDNAの品質を確認する。"],
       "top_n":4}'
```

`results` が `relevance_score` の降順で返る。スコアは0〜1の範囲。

実機での結果（CPU、`compose.cpu.yaml`）: PCR関連の2件が0.977 / 0.972、無関係な2件は0.0002未満で、正しく並べ替えられた。
スコアが0〜1でよく分離するため、RAGで「根拠がない」と判定するしきい値にそのまま使える。

## 3. GPU機での確認（未実施）

GPU機（本番相当: RTX 3090 24GB）で、次を確認する。

- [ ] `reranker` が `healthy` になり、ログにCUDAデバイスが表示される
- [ ] 上記2の `/v1/rerank` が応答する
- [ ] 候補20件（各約1000字）のrerankにかかる時間（目安: 1秒以内）
- [ ] `embedding` + `reranker` + `llm` の同時稼働時のVRAM使用量（`nvidia-smi`）

```bash
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

## 既知の制約

- CPUでは遅い。候補20件（各約550字）で約177秒かかった（WSL2、RAM 7.7GB）。RAM 8GB程度の開発機では
  rerankerを起動せず、単体テスト（モック）で開発する（[cpu-dev-setup.md](cpu-dev-setup.md) 参照）。
