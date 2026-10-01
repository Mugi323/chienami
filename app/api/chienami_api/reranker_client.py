"""Reranker（llama.cpp --reranking, Qwen3-Reranker-0.6B, Issue #50）クライアント。"""

from __future__ import annotations

import httpx


class RerankerClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> RerankerClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def rerank(self, query: str, texts: list[str]) -> list[tuple[int, float]]:
        """textsの各要素とqueryの関連度を求め、(textsのindex, スコア0〜1) を降順で返す。"""
        if not texts:
            return []
        resp = self._client.post(
            "/v1/rerank",
            json={"query": query, "documents": texts, "top_n": len(texts)},
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        ranked = [(int(r["index"]), float(r["relevance_score"])) for r in results]
        if any(not 0 <= index < len(texts) for index, _ in ranked):
            raise RuntimeError("reranker returned an out-of-range index")
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked
