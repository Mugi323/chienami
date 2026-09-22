"""text-embeddings-inference (TEI) クライアント。

chienami-indexer（app/indexer/chienami_indexer/embedding_client.py）と同一の
小さなクライアントを、サービス間の共有パッケージ化はせずあえて複製している。
両サービスとも単一メソッドの薄いラッパーであり、共有ライブラリを新設するほどの
重複ではないと判断した。
"""

from __future__ import annotations

import httpx


class EmbeddingClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
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
