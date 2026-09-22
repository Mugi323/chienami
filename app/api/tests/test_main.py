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
