import httpx
import pytest

from chienami_api.reranker_client import RerankerClient


def _client(handler) -> RerankerClient:
    client = RerankerClient("http://reranker:80")
    client._client = httpx.Client(
        base_url="http://reranker:80", transport=httpx.MockTransport(handler)
    )
    return client


def test_rerank_posts_documents_and_sorts_by_score():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 0, "relevance_score": 0.2},
                    {"index": 1, "relevance_score": 0.9},
                ]
            },
        )

    ranked = _client(handler).rerank("質問", ["a", "b"])
    assert ranked == [(1, 0.9), (0, 0.2)]
    assert seen["path"] == "/v1/rerank"
    assert '"top_n":2' in seen["body"].replace(" ", "")


def test_rerank_empty_texts_does_not_call_server():
    def handler(request):
        raise AssertionError("should not be called")

    assert _client(handler).rerank("質問", []) == []


def test_rerank_rejects_out_of_range_index():
    def handler(request):
        return httpx.Response(200, json={"results": [{"index": 5, "relevance_score": 0.5}]})

    with pytest.raises(RuntimeError):
        _client(handler).rerank("質問", ["a"])


def test_rerank_raises_on_http_error():
    with pytest.raises(httpx.HTTPStatusError):
        _client(lambda request: httpx.Response(503)).rerank("質問", ["a"])
