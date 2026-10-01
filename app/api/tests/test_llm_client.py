import json

import httpx
import pytest

from chienami_api.llm_client import LLMClient


def _client(handler, api_key="secret") -> LLMClient:
    client = LLMClient("http://llm:80", api_key, max_tokens=256)
    client._client = httpx.Client(
        base_url="http://llm:80",
        headers=client._client.headers,
        transport=httpx.MockTransport(handler),
    )
    return client


def _response(content, finish_reason="stop"):
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]},
    )


def test_chat_sends_messages_with_thinking_disabled_and_auth():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.read())
        return _response("答え[S1]")

    messages = [{"role": "user", "content": "質問"}]
    assert _client(handler).chat(messages) == "答え[S1]"
    assert seen["path"] == "/v1/chat/completions"
    assert seen["auth"] == "Bearer secret"
    assert seen["body"]["messages"] == messages
    assert seen["body"]["max_tokens"] == 256
    assert seen["body"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_chat_omits_auth_header_without_api_key():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return _response("ok")

    _client(handler, api_key="").chat([])
    assert seen["auth"] is None


def test_chat_strips_empty_think_block():
    assert _client(lambda r: _response("<think>\n\n</think>\n\n答え")).chat([]) == "答え"


def test_chat_raises_on_empty_content():
    with pytest.raises(RuntimeError, match="length"):
        _client(lambda r: _response("", finish_reason="length")).chat([])
    with pytest.raises(RuntimeError):
        _client(lambda r: _response(None)).chat([])


def test_chat_raises_on_http_error():
    with pytest.raises(httpx.HTTPStatusError):
        _client(lambda r: httpx.Response(401)).chat([])
