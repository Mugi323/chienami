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


# --- /chat（Phase 4 RAG） ---


def test_chat_returns_answer_with_sources(monkeypatch):
    from chienami_api.rag import RagAnswer, Source
    from chienami_api.search import Chunk

    chunk = Chunk("d1", "PCR手順", "https://knowledge.lab.local/doc/d1", 2, "58度", 0.95)
    captured = {}

    def _answer(question, top_k=None, history=None):
        captured.update(question=question, top_k=top_k, history=history)
        return RagAnswer(
            "58度です[S1]。",
            abstained=False,
            sources=[Source("S1", chunk, cited=True)],
            timings_ms={"search_ms": 10, "rerank_ms": 20, "llm_ms": 30},
        )

    monkeypatch.setattr(main.rag_service, "answer", _answer)
    resp = client.post("/chat", json={"question": "  温度は？ ", "top_k": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert captured == {"question": "温度は？", "top_k": 3, "history": []}
    assert body["answer"] == "58度です[S1]。"
    assert body["abstained"] is False
    assert body["sources"] == [
        {
            "id": "S1",
            "document_id": "d1",
            "title": "PCR手順",
            "url": "https://knowledge.lab.local/doc/d1",
            "snippet": "58度",
            "score": 0.95,
            "chunk_index": 2,
            "cited": True,
        }
    ]
    assert body["timings"] == {"search_ms": 10, "rerank_ms": 20, "llm_ms": 30}


def test_chat_passes_history(monkeypatch):
    from chienami_api.rag import RagAnswer, Turn

    captured = {}

    def _answer(question, top_k=None, history=None):
        captured["history"] = history
        return RagAnswer("答え", abstained=False, sources=[], timings_ms={})

    monkeypatch.setattr(main.rag_service, "answer", _answer)
    resp = client.post(
        "/chat",
        json={
            "question": "その手順は？",
            "history": [
                {"role": "user", "content": "PCRとは？"},
                {"role": "assistant", "content": "DNAを増やす方法です。"},
            ],
        },
    )
    assert resp.status_code == 200
    assert captured["history"] == [
        Turn("user", "PCRとは？"),
        Turn("assistant", "DNAを増やす方法です。"),
    ]


def test_chat_validates_request():
    assert client.post("/chat", json={}).status_code == 422
    assert client.post("/chat", json={"question": ""}).status_code == 422
    assert client.post("/chat", json={"question": "   "}).status_code == 422
    assert client.post("/chat", json={"question": "q", "top_k": 0}).status_code == 422
    assert client.post("/chat", json={"question": "q", "top_k": 11}).status_code == 422
    bad_role = {"question": "q", "history": [{"role": "system", "content": "x"}]}
    assert client.post("/chat", json=bad_role).status_code == 422


def test_chat_returns_503_when_ai_service_down(monkeypatch):
    from chienami_api.rag import AIServiceError

    def _raise(question, top_k=None, history=None):
        raise AIServiceError("llm error")

    monkeypatch.setattr(main.rag_service, "answer", _raise)
    assert client.post("/chat", json={"question": "q"}).status_code == 503


def test_chat_returns_502_when_embedding_down(monkeypatch):
    from chienami_api.rag import EmbeddingError

    def _raise(question, top_k=None, history=None):
        raise EmbeddingError("down")

    monkeypatch.setattr(main.rag_service, "answer", _raise)
    assert client.post("/chat", json={"question": "q"}).status_code == 502


def test_search_still_works_when_ai_services_are_down(monkeypatch):
    # LLM/Rerankerの状態に関わらず、mode=semanticの検索は呼び出さない。
    def _boom(*args, **kwargs):
        raise AssertionError("AI services must not be called by semantic search")

    monkeypatch.setattr(main.embedding_client, "embed", lambda texts: [[0.1]])
    monkeypatch.setattr(main.search_service, "search", lambda vector, limit: [])
    monkeypatch.setattr(main.reranker_client, "rerank", _boom)
    monkeypatch.setattr(main.llm_client, "chat", _boom)
    assert client.get("/search", params={"q": "PCR"}).status_code == 200


def test_points_returns_ranking(monkeypatch):
    from chienami_api.points import UserPoints

    monkeypatch.setattr(main.points_service, "_source", object())
    monkeypatch.setattr(
        main.points_service,
        "ranking",
        lambda: (1700000000.0, [UserPoints(1, "u1", "佐藤", 3, 1200, 42)]),
    )
    resp = client.get("/points")
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated_at"] == 1700000000.0
    assert body["rules"] == {
        "points_per_document": main.POINTS_PER_DOCUMENT,
        "characters_per_point": main.POINTS_CHARACTERS_PER_POINT,
    }
    assert body["users"] == [
        {
            "rank": 1,
            "user_id": "u1",
            "name": "佐藤",
            "documents": 3,
            "characters": 1200,
            "points": 42,
        }
    ]


def test_points_without_outline_token_returns_503(monkeypatch):
    monkeypatch.setattr(main.points_service, "_source", None)
    resp = client.get("/points")
    assert resp.status_code == 503


def test_points_outline_failure_returns_502(monkeypatch):
    def _raise():
        raise RuntimeError("boom")

    monkeypatch.setattr(main.points_service, "_source", object())
    monkeypatch.setattr(main.points_service, "ranking", _raise)
    resp = client.get("/points")
    assert resp.status_code == 502
