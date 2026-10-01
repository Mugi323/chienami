# RAG（/chat）の動作確認（Phase 4）

chienami-api の `POST /chat` は、研究室の知識ベースを根拠にした**出典付き回答**を返す。
実装は `app/api/chienami_api/rag.py`、APIの形はdesign書10章の「Phase 4 chatリクエスト/レスポンス例」を参照。

## 処理の流れ

1. 質問をEmbeddingする
2. ハイブリッド検索の候補を集める（Dense + Keyword → RRF、上位 `API_HYBRID_CANDIDATES` 件。
   [search-api-setup.md](search-api-setup.md) 4節）
3. Reranker（[reranker-setup.md](reranker-setup.md)）で関連度順に並べ替える
4. 関連度が `RAG_MIN_RERANK_SCORE`（既定0.3）以上の上位 `RAG_TOP_K`（既定5）件を根拠として選ぶ
5. **根拠が1件もなければ、LLMを呼ばずに回答を控える**（`abstained: true`）
6. 根拠に `[S1]`〜`[Sk]` を付けてLLMに渡す。system promptはdesign書5.2節の3原則
   （根拠にない内容を断定しない / 分からなければ「資料からは分かりません。」と答える / 各文にSource IDを付ける）
7. 回答中の `[Sn]` を拾い、各根拠に `cited` を付けて返す

LLM（Qwen3）の思考モードは無効にして呼び出す（[llm-setup.md](llm-setup.md) の既知の制約への対応）。

## 障害時の挙動

| 状況 | `/chat` | `/search` |
| --- | --- | --- |
| Embedding停止 | 502 | 502 |
| Reranker停止 | 503 | semantic: 正常 / hybrid: RRF順で返す |
| LLM停止 | 503（根拠なしで回答を控える場合は200） | 正常 |

`api` サービスの `depends_on` に `llm` / `reranker` は入れていない。AI系が止まっていても、
検索（Phase 3の価値）は使い続けられる。

## 設定（config/docker.env）

| 変数 | 既定値 | 意味 |
| --- | --- | --- |
| `RAG_TOP_K` | 5 | LLMに渡す根拠の最大件数（リクエストの `top_k` で1〜10の範囲で上書き可） |
| `RAG_MIN_RERANK_SCORE` | 0.3 | 根拠として採用するRerank関連度の下限 |
| `LLM_MAX_TOKENS` | 1024 | 回答の最大生成トークン数 |
| `LLM_TIMEOUT_SECONDS` | 120 | LLM応答待ちのタイムアウト |
| `API_HYBRID_CANDIDATES` | 20 | Rerankerに渡す候補チャンク数 |

ログには、根拠の件数・引用された件数・回答を控えたかどうか・各段階の処理時間を出す。
質問本文はログに出さない。

## 動作確認

```bash
cd app
docker compose run --rm --no-deps --entrypoint sh outline -c \
  "wget -qO- --header='Content-Type: application/json' \
   --post-data='{\"question\":\"PCRのアニーリング温度は？\"}' http://api:8000/chat"
```

ブラウザからは、Reverse Proxy経由で `https://search.lab.local/api/chat` に届く。

## GPU機での確認（未実施）

開発機（GPUなし、RAM 7.7GB）では、モデルのコンテナを動かさずにユニットテスト（外部サービスはモック）だけで
開発した（[cpu-dev-setup.md](cpu-dev-setup.md)）。GPU機で次を確認する。

- [ ] `embedding` / `reranker` / `llm` / `api` がすべて `healthy`
- [ ] 知識ベースにある内容を質問すると、`[Sn]` 付きの回答が返り、`sources` の `url` から元のOutlineページを開ける
- [ ] 知識ベースにない内容（例: 「明日の天気は？」）を質問すると、`abstained: true` になる
- [ ] `timings` の各値（目安: 合計10秒以内）
- [ ] `RAG_MIN_RERANK_SCORE` の妥当性（代表的な質問で、関連する文書の関連度と無関係な文書の関連度を見比べて調整する）
- [ ] `docker compose stop llm reranker` の状態で、`/search` が動き、`/chat` が503を返す
