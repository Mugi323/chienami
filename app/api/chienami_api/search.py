"""Qdrantへの検索（Dense / Keyword / Hybrid）と、文書単位での重複排除。

Hybrid検索（Phase 4, design書5.2節）の流れ:
  Dense候補 + Keyword候補 → RRFで統合 → Rerankerで並べ替え
Keyword候補もSemantic Searchと同じQdrant索引から取るため、検索対象の範囲
（全員閲覧可Collectionのみ）はSemantic Searchと一致する。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from typing import Any, Protocol

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

logger = logging.getLogger("chienami-api")


@dataclass(frozen=True)
class SearchResult:
    document_id: str
    title: str
    url: str
    score: float
    snippet: str
    chunk_index: int


@dataclass(frozen=True)
class Chunk:
    """検索候補の1チャンク。scoreの意味は取得段階（Dense/Keyword/RRF/Rerank）で変わる。"""

    document_id: str
    title: str
    url: str
    chunk_index: int
    text: str
    score: float

    @property
    def key(self) -> tuple[str, int]:
        return (self.document_id, self.chunk_index)


class _PointLike(Protocol):
    payload: dict[str, Any] | None


class _ScoredPointLike(_PointLike, Protocol):
    score: float


class Reranker(Protocol):
    def rerank(self, query: str, texts: list[str]) -> list[tuple[int, float]]: ...


def point_to_chunk(point: _PointLike, score: float) -> Chunk | None:
    payload = point.payload or {}
    document_id = payload.get("document_id")
    if not document_id:
        return None
    return Chunk(
        document_id=document_id,
        title=payload.get("title", ""),
        url=payload.get("url", ""),
        chunk_index=payload.get("chunk_index", 0),
        text=payload.get("text", ""),
        score=score,
    )


def dedupe_chunks(chunks: list[Chunk], limit: int) -> list[SearchResult]:
    """同一文書の複数チャンクがある場合、先に現れた（=スコアの高い）チャンクのみ残す。

    chunksはスコア降順に並んでいる前提。
    """
    seen: set[str] = set()
    results: list[SearchResult] = []
    for chunk in chunks:
        if chunk.document_id in seen:
            continue
        seen.add(chunk.document_id)
        results.append(
            SearchResult(
                document_id=chunk.document_id,
                title=chunk.title,
                url=chunk.url,
                score=chunk.score,
                snippet=chunk.text,
                chunk_index=chunk.chunk_index,
            )
        )
        if len(results) >= limit:
            break
    return results


def dedupe_by_document(hits: list[_ScoredPointLike], limit: int) -> list[SearchResult]:
    """Qdrantの検索結果（スコア降順）を文書単位で重複排除する。"""
    chunks = [c for hit in hits if (c := point_to_chunk(hit, hit.score)) is not None]
    return dedupe_chunks(chunks, limit)


# 漢字・カタカナ・英数字の連続をキーワードとして取り出す。ひらがなは助詞・活用語尾が
# 大半でキーワードになりにくいため対象外とする。
_KEYWORD_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._+\-/]*[A-Za-z0-9]"  # 英数字（型番・試薬名・コマンド等）
    r"|[ァ-ヺー]{2,}"  # カタカナ
    r"|[一-鿿々]{2,}"  # 漢字（々を含む）
)
_MAX_KEYWORDS = 8


def extract_keywords(query: str) -> list[str]:
    """クエリからKeyword検索に使う語を取り出す（出現順・重複なし、最大8語）。"""
    keywords: list[str] = []
    seen: set[str] = set()
    for match in _KEYWORD_PATTERN.finditer(query):
        word = match.group(0)
        folded = word.lower()
        if folded in seen:
            continue
        seen.add(folded)
        keywords.append(word)
        if len(keywords) >= _MAX_KEYWORDS:
            break
    return keywords


def keyword_score(text: str, keywords: list[str]) -> int:
    """textに含まれるキーワードの種類数（英字は大文字小文字を区別しない）。"""
    folded = text.lower()
    return sum(1 for kw in keywords if kw.lower() in folded)


def rrf_fuse(rankings: list[list[Chunk]], k: int = 60) -> list[Chunk]:
    """Reciprocal Rank Fusionで複数の順位付けを統合する。

    同一チャンク（document_id, chunk_index）は1つにまとめ、scoreをRRFスコアに置き換える。
    """
    scores: dict[tuple[str, int], float] = {}
    first_seen: dict[tuple[str, int], Chunk] = {}
    for ranking in rankings:
        for rank, chunk in enumerate(ranking, start=1):
            scores[chunk.key] = scores.get(chunk.key, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(chunk.key, chunk)
    fused = [replace(first_seen[key], score=score) for key, score in scores.items()]
    fused.sort(key=lambda c: c.score, reverse=True)
    return fused


def rerank_chunks(query: str, chunks: list[Chunk], reranker: Reranker) -> list[Chunk]:
    """Rerankerの関連度スコアでchunksを並べ替える（scoreは関連度0〜1に置き換わる）。"""
    if not chunks:
        return []
    ranked = reranker.rerank(query, [c.text for c in chunks])
    return [replace(chunks[index], score=score) for index, score in ranked]


class SearchService:
    def __init__(
        self,
        qdrant: QdrantClient,
        collection: str,
        overfetch_factor: int = 5,
        keyword_scan_limit: int = 200,
    ) -> None:
        self._qdrant = qdrant
        self._collection = collection
        self._overfetch_factor = overfetch_factor
        self._keyword_scan_limit = keyword_scan_limit

    def search(self, query_vector: list[float], limit: int) -> list[SearchResult]:
        """Semantic Search（Phase 3）。文書単位で重複排除して返す。"""
        response = self._qdrant.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=limit * self._overfetch_factor,
            with_payload=True,
        )
        return dedupe_by_document(response.points, limit)

    def dense_chunks(self, query_vector: list[float], limit: int) -> list[Chunk]:
        response = self._qdrant.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=limit,
            with_payload=True,
        )
        return [c for p in response.points if (c := point_to_chunk(p, p.score)) is not None]

    def keyword_chunks(self, keywords: list[str], limit: int) -> list[Chunk]:
        """いずれかのキーワードを含むチャンクを、含むキーワードの種類数の多い順に返す。"""
        if not keywords:
            return []
        points, _ = self._qdrant.scroll(
            collection_name=self._collection,
            scroll_filter=qmodels.Filter(
                should=[
                    qmodels.FieldCondition(key="text", match=qmodels.MatchText(text=kw))
                    for kw in keywords
                ]
            ),
            limit=self._keyword_scan_limit,
            with_payload=True,
            with_vectors=False,
        )
        chunks = [c for p in points if (c := point_to_chunk(p, 0.0)) is not None]
        scored = [replace(c, score=float(keyword_score(c.text, keywords))) for c in chunks]
        scored = [c for c in scored if c.score > 0]
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:limit]

    def candidate_chunks(
        self, query: str, query_vector: list[float], candidates: int
    ) -> list[Chunk]:
        """Dense + KeywordをRRFで統合し、上位candidates件を返す（Rerank前の候補）。"""
        dense = self.dense_chunks(query_vector, candidates)
        keyword = self.keyword_chunks(extract_keywords(query), candidates)
        return rrf_fuse([dense, keyword])[:candidates]

    def hybrid_chunks(
        self,
        query: str,
        query_vector: list[float],
        candidates: int,
        reranker: Reranker | None,
    ) -> list[Chunk]:
        """Dense + KeywordをRRFで統合し、上位candidates件をRerankerで並べ替えて返す。

        Rerankerがない・失敗した場合はRRF順のまま返す（検索自体は止めない）。
        """
        fused = self.candidate_chunks(query, query_vector, candidates)
        if reranker is None:
            return fused
        try:
            return rerank_chunks(query, fused, reranker)
        except Exception:
            logger.exception("Rerankに失敗したため、RRF順の結果を返します")
            return fused
