"""Qdrant格納処理。

design書4.3節: Qdrantには「原文そのものの正本」を置かず、検索用チャンク・Embedding・
metadataのみを保存する。索引は全削除してもOutlineから再構築できる設計とする。
"""

from __future__ import annotations

import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

# document_id + chunk_index から決定論的にpoint IDを作るための固定名前空間。
# 再索引時に同じ文書・同じchunk_indexなら同じpoint IDになり、upsertで上書きされる。
_POINT_NAMESPACE = uuid.UUID("d9b1c8b2-6e2b-4f2a-9a9d-2a6a6f3b7a10")

# chienami-apiのKeyword検索が全文マッチに使うpayloadフィールド。
TEXT_INDEX_FIELD = "text"


def point_id(document_id: str, chunk_index: int) -> str:
    return str(uuid.uuid5(_POINT_NAMESPACE, f"{document_id}:{chunk_index}"))


class QdrantStore:
    def __init__(self, url: str, api_key: str, collection: str, vector_size: int) -> None:
        self._client = QdrantClient(url=url, api_key=api_key)
        self._collection = collection
        self._vector_size = vector_size

    def ensure_collection(self) -> None:
        existing = {c.name for c in self._client.get_collections().collections}
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=qmodels.VectorParams(
                    size=self._vector_size, distance=qmodels.Distance.COSINE
                ),
            )
        self.ensure_text_index()

    def ensure_text_index(self) -> None:
        """Keyword検索（Phase 4 Hybrid検索）用に、本文(text)の全文インデックスを作る。

        multilingual tokenizerは日本語の単語分割に対応する。Phase 3で作成済みの
        collectionにも後から追加できるよう、インデックスが無い場合だけ作成する。
        """
        info = self._client.get_collection(self._collection)
        if TEXT_INDEX_FIELD in (info.payload_schema or {}):
            return
        self._client.create_payload_index(
            collection_name=self._collection,
            field_name=TEXT_INDEX_FIELD,
            field_schema=qmodels.TextIndexParams(
                type=qmodels.TextIndexType.TEXT,
                tokenizer=qmodels.TokenizerType.MULTILINGUAL,
                lowercase=True,
            ),
        )

    def get_document_hash(self, document_id: str) -> str | None:
        """指定document_idの既存チャンクからcontent_hashを1件取得する
        （同一文書内のチャンクは全て同じcontent_hashを持つため代表1件で足りる）。"""
        points, _ = self._client.scroll(
            collection_name=self._collection,
            scroll_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="document_id", match=qmodels.MatchValue(value=document_id)
                    )
                ]
            ),
            limit=1,
            with_payload=["content_hash"],
            with_vectors=False,
        )
        if not points:
            return None
        return points[0].payload.get("content_hash") if points[0].payload else None

    def delete_document(self, document_id: str) -> None:
        self._client.delete(
            collection_name=self._collection,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="document_id", match=qmodels.MatchValue(value=document_id)
                        )
                    ]
                )
            ),
        )

    def upsert_chunks(
        self,
        document_id: str,
        collection_id: str,
        title: str,
        url: str,
        content_hash: str,
        updated_at: str,
        chunks: list[str],
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        points = [
            qmodels.PointStruct(
                id=point_id(document_id, i),
                vector=vector,
                payload={
                    "document_id": document_id,
                    "collection_id": collection_id,
                    "title": title,
                    "url": url,
                    "content_hash": content_hash,
                    "updated_at": updated_at,
                    "chunk_index": i,
                    "text": chunk,
                },
            )
            for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        ]
        if points:
            self._client.upsert(collection_name=self._collection, points=points)

    def known_document_ids(self) -> set[str]:
        """Qdrantに現存する全document_idを集める。Outline側で削除・非公開化された
        文書の孤立チャンクを検出し、後続で削除するために使う。"""
        ids: set[str] = set()
        next_offset = None
        while True:
            points, next_offset = self._client.scroll(
                collection_name=self._collection,
                limit=200,
                with_payload=["document_id"],
                with_vectors=False,
                offset=next_offset,
            )
            for p in points:
                doc_id = p.payload.get("document_id") if p.payload else None
                if doc_id:
                    ids.add(doc_id)
            if next_offset is None:
                break
        return ids
