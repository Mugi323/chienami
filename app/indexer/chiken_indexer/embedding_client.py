"""text-embeddings-inference (TEI) クライアント。"""

from __future__ import annotations

import httpx


class EmbeddingClient:
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> EmbeddingClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._client.post("/embed", json={"inputs": texts, "truncate": True})
        resp.raise_for_status()
        vectors = resp.json()
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"embedding count mismatch: sent {len(texts)} texts, got {len(vectors)} vectors"
            )
        return vectors
