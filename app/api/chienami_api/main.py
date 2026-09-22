"""chienami-api エントリポイント。

Phase 3はLLMを使用せず、検索結果を返した時点で終了する（design書5.2節）。
検索結果は必ず元のOutlineページを開けるURLを含める。
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from qdrant_client import QdrantClient

from .embedding_client import EmbeddingClient
from .search import SearchService

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("chienami-api")


def _env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"環境変数が未設定です: {name}")
    return value or ""


EMBEDDING_URL = _env("EMBEDDING_URL", "http://embedding:80")
QDRANT_URL = _env("QDRANT_URL", "http://qdrant:6333")
QDRANT_API_KEY = _env("QDRANT_API_KEY", required=True)
QDRANT_COLLECTION = _env("QDRANT_COLLECTION", "chienami_documents")
SEARCH_DEFAULT_LIMIT = int(_env("API_SEARCH_DEFAULT_LIMIT", "10"))
SEARCH_MAX_LIMIT = int(_env("API_SEARCH_MAX_LIMIT", "50"))

app = FastAPI(title="Chienami API")

qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
search_service = SearchService(qdrant_client, QDRANT_COLLECTION)
embedding_client = EmbeddingClient(EMBEDDING_URL)


class SearchResultResponse(BaseModel):
    document_id: str
    title: str
    url: str
    score: float
    snippet: str
    chunk_index: int


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultResponse]


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, description="検索クエリ"),
    limit: int = Query(SEARCH_DEFAULT_LIMIT, ge=1, le=SEARCH_MAX_LIMIT),
) -> SearchResponse:
    try:
        vectors = embedding_client.embed([q])
    except Exception as exc:
        logger.exception("Embedding取得に失敗しました")
        raise HTTPException(status_code=502, detail="embedding service error") from exc

    if not vectors:
        raise HTTPException(status_code=502, detail="embedding service returned no vector")

    try:
        results = search_service.search(vectors[0], limit=limit)
    except Exception as exc:
        logger.exception("Qdrant検索に失敗しました")
        raise HTTPException(status_code=502, detail="search backend error") from exc

    return SearchResponse(
        query=q,
        results=[SearchResultResponse(**r.__dict__) for r in results],
    )
