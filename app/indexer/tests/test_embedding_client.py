import httpx
import pytest
import respx

from chienami_indexer.embedding_client import EmbeddingClient


def test_embed_empty_list_returns_empty_without_request():
    with EmbeddingClient("http://embedding.test") as client:
        assert client.embed([]) == []


@respx.mock
def test_embed_returns_vectors():
    respx.post("http://embedding.test/embed").mock(
        return_value=httpx.Response(200, json=[[0.1, 0.2], [0.3, 0.4]])
    )

    with EmbeddingClient("http://embedding.test") as client:
        vectors = client.embed(["a", "b"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


@respx.mock
def test_embed_count_mismatch_raises():
    respx.post("http://embedding.test/embed").mock(
        return_value=httpx.Response(200, json=[[0.1, 0.2]])
    )

    with EmbeddingClient("http://embedding.test") as client, pytest.raises(RuntimeError):
        client.embed(["a", "b"])
