"""LLM（llama.cpp, OpenAI互換API, Issue #48）クライアント。"""

from __future__ import annotations

import re

import httpx

# Qwen3は思考モードを無効にしても、空の <think></think> を出力することがあるため取り除く。
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout: float = 120.0,
    ) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout)
        self._max_tokens = max_tokens
        self._temperature = temperature

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> LLMClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def chat(self, messages: list[dict[str, str]]) -> str:
        """messagesを送り、応答本文を返す。

        Qwen3は既定で思考モードを使い、max_tokensを思考で使い切ると content が空になる
        （docs/design/llm-setup.md）。RAGでは思考は不要なため無効にする。
        """
        resp = self._client.post(
            "/v1/chat/completions",
            json={
                "messages": messages,
                "max_tokens": self._max_tokens,
                "temperature": self._temperature,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        resp.raise_for_status()
        choice = resp.json()["choices"][0]
        content = _THINK_BLOCK.sub("", choice["message"].get("content") or "").strip()
        if not content:
            raise RuntimeError(
                f"LLM returned empty content (finish_reason={choice.get('finish_reason')})"
            )
        return content
