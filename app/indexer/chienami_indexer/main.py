"""chienami-indexer エントリポイント。

一定間隔（INDEXER_INTERVAL_SECONDS）でOutlineの「全員閲覧可Collection」内の公開済み
文書を取得し、変更があったものだけEmbeddingしてQdrantへ格納する（design書5.1節）。
"""

from __future__ import annotations

import logging
import os
import time

from .chunking import chunk_text
from .embedding_client import EmbeddingClient
from .hashing import content_hash
from .outline_client import OutlineClient
from .store import QdrantStore

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("chienami-indexer")

# Qwen3-Embedding-0.6Bの出力次元数（design書4.4節）。
EMBEDDING_VECTOR_SIZE = 1024


def _env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"環境変数が未設定です: {name}")
    return value or ""


def run_once(
    outline: OutlineClient,
    embedding: EmbeddingClient,
    store: QdrantStore,
    public_url: str,
    chunk_size: int,
    chunk_overlap: int,
) -> None:
    store.ensure_collection()

    seen_document_ids: set[str] = set()
    collections = outline.list_public_collections()
    logger.info("索引対象Collection数: %d", len(collections))

    for collection in collections:
        for document in outline.iter_published_documents(collection.id):
            seen_document_ids.add(document.id)
            doc_hash = content_hash(document.text)
            existing_hash = store.get_document_hash(document.id)
            if existing_hash == doc_hash:
                continue

            chunks = chunk_text(document.text, chunk_size=chunk_size, overlap=chunk_overlap)
            store.delete_document(document.id)
            if not chunks:
                continue

            vectors = embedding.embed([c.text for c in chunks])
            store.upsert_chunks(
                document_id=document.id,
                collection_id=document.collection_id,
                title=document.title,
                url=f"{public_url.rstrip('/')}{document.url}",
                content_hash=doc_hash,
                updated_at=document.updated_at,
                chunks=[c.text for c in chunks],
                vectors=vectors,
            )
            logger.info(
                "索引更新: document_id=%s title=%r chunks=%d",
                document.id,
                document.title,
                len(chunks),
            )

    stale_ids = store.known_document_ids() - seen_document_ids
    for doc_id in stale_ids:
        logger.info("索引から削除（Outline側で非公開化/削除/アーカイブ済み）: %s", doc_id)
        store.delete_document(doc_id)


def main() -> None:
    outline_url = _env("OUTLINE_INTERNAL_URL", "http://outline:3000")
    outline_token = _env("OUTLINE_API_TOKEN", required=True)
    public_url = _env("URL", required=True)
    embedding_url = _env("EMBEDDING_URL", "http://embedding:80")
    qdrant_url = _env("QDRANT_URL", "http://qdrant:6333")
    qdrant_api_key = _env("QDRANT_API_KEY", required=True)
    qdrant_collection = _env("QDRANT_COLLECTION", "chienami_documents")
    interval = int(_env("INDEXER_INTERVAL_SECONDS", "600"))
    chunk_size = int(_env("INDEXER_CHUNK_SIZE", "1000"))
    chunk_overlap = int(_env("INDEXER_CHUNK_OVERLAP", "100"))

    store = QdrantStore(qdrant_url, qdrant_api_key, qdrant_collection, EMBEDDING_VECTOR_SIZE)

    while True:
        try:
            with OutlineClient(outline_url, outline_token) as outline, EmbeddingClient(
                embedding_url
            ) as embedding:
                run_once(outline, embedding, store, public_url, chunk_size, chunk_overlap)
            logger.info("索引化サイクル完了。次回まで%d秒待機します", interval)
        except Exception:
            logger.exception("索引化サイクルでエラーが発生しました。次回サイクルで再試行します")
        time.sleep(interval)


if __name__ == "__main__":
    main()
