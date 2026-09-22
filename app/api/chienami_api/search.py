"""Qdrantへのベクトル検索と、文書単位での重複排除。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from qdrant_client import QdrantClient


@dataclass(frozen=True)
class SearchResult:
    document_id: str
    title: str
    url: str
    score: float
    snippet: str
    chunk_index: int


class _ScoredPointLike(Protocol):
    score: float
    payload: dict[str, Any] | None


def dedupe_by_document(hits: list[_ScoredPointLike], limit: int) -> list[SearchResult]:
    """同一文書の複数チャンクがヒットした場合、最もスコアの高いチャンクのみ残す。

    Qdrantの検索結果はスコア降順で返る前提（query_points のデフォルト挙動）。
    """
    seen: set[str] = set()
    results: list[SearchResult] = []
    for hit in hits:
        payload = hit.payload or {}
        document_id = payload.get("document_id")
        if not document_id or document_id in seen:
            continue
        seen.add(document_id)
        results.append(
            SearchResult(
                document_id=document_id,
                title=payload.get("title", ""),
                url=payload.get("url", ""),
                score=hit.score,
                snippet=payload.get("text", ""),
                chunk_index=payload.get("chunk_index", 0),
            )
        )
        if len(results) >= limit:
            break
    return results


class SearchService:
    def __init__(self, qdrant: QdrantClient, collection: str, overfetch_factor: int = 5) -> None:
        self._qdrant = qdrant
        self._collection = collection
        self._overfetch_factor = overfetch_factor

    def search(self, query_vector: list[float], limit: int) -> list[SearchResult]:
        response = self._qdrant.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=limit * self._overfetch_factor,
            with_payload=True,
        )
        return dedupe_by_document(response.points, limit)
