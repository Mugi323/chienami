import os

os.environ.setdefault("QDRANT_API_KEY", "test-key")

from fastapi.testclient import TestClient  # noqa: E402

from chienami_api import main  # noqa: E402
from chienami_api.search import SearchResult  # noqa: E402

client = TestClient(main.app)


def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_search_returns_results(monkeypatch):
    monkeypatch.setattr(main.embedding_client, "embed", lambda texts: [[0.1, 0.2, 0.3]])
    monkeypatch.setattr(
        main.search_service,
        "search",
        lambda vector, limit: [
            SearchResult(
                document_id="d1",
                title="タイトル",
                url="https://knowledge.lab.local/doc/d1",
                score=0.9,
                snippet="本文の一部",
                chunk_index=0,
            )
        ],
    )

    resp = client.get("/search", params={"q": "テスト"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "テスト"
    assert body["results"][0]["document_id"] == "d1"
    assert body["results"][0]["url"] == "https://knowledge.lab.local/doc/d1"


def test_search_requires_query():
    resp = client.get("/search")
    assert resp.status_code == 422


def test_search_embedding_failure_returns_502(monkeypatch):
    def _raise(texts):
        raise RuntimeError("boom")

    monkeypatch.setattr(main.embedding_client, "embed", _raise)
    resp = client.get("/search", params={"q": "テスト"})
    assert resp.status_code == 502


def test_search_hybrid_mode_dedupes_reranked_chunks(monkeypatch):
    from chienami_api.search import Chunk

    def _chunk(doc, idx, score):
        return Chunk(doc, f"t{doc}", f"https://knowledge.lab.local/doc/{doc}", idx, "本文", score)

    captured = {}

    def _hybrid(query, vector, candidates, reranker):
        captured.update(query=query, candidates=candidates)
        return [_chunk("d2", 3, 0.9), _chunk("d2", 0, 0.8), _chunk("d1", 0, 0.5)]

    monkeypatch.setattr(main.embedding_client, "embed", lambda texts: [[0.1]])
    monkeypatch.setattr(main.search_service, "hybrid_chunks", _hybrid)

    resp = client.get("/search", params={"q": "PCR", "mode": "hybrid", "limit": 5})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert [(r["document_id"], r["chunk_index"]) for r in results] == [("d2", 3), ("d1", 0)]
    assert captured == {"query": "PCR", "candidates": main.HYBRID_CANDIDATES}


def test_search_rejects_unknown_mode():
    resp = client.get("/search", params={"q": "PCR", "mode": "magic"})
    assert resp.status_code == 422
