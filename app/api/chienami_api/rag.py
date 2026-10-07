"""出典付きRAG回答（Phase 4, design書5.2節）。

流れ:
  質問をEmbedding → Hybrid検索の候補（Dense + Keyword → RRF）→ Rerank
  → 関連度がしきい値以上の上位k件を根拠として選ぶ
  → 根拠が1件もなければLLMを呼ばずに回答を控える
  → [S1]..[Sk] を付けた根拠をLLMに渡し、各主張にSource IDを付けて回答させる

プロンプト組み立て・引用抽出・根拠選択は純関数にしてI/Oと分け、単体テストしやすくしている。
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Protocol

from .search import Chunk, Reranker, SearchService, rerank_chunks

logger = logging.getLogger("chienami-api")

# design書5.2節の3原則（根拠にない内容を断定しない / 不明なら不明と答える / Source IDを示す）。
NO_ANSWER_TEXT = "資料からは分かりません。"
SYSTEM_PROMPT = f"""あなたは研究室の知識ベース「Chienami」のアシスタントです。
ユーザーの質問に、与えられた資料だけを根拠として日本語で答えてください。

規則:
1. 資料に書かれていない内容を断定しないこと。推測や一般知識で補わないこと。
2. 資料から答えが分からない場合は「{NO_ANSWER_TEXT}」とだけ答えること。
3. 各文の末尾に、根拠とした資料のSource IDを [S1] のように付けること。
   複数ある場合は [S1][S3] のように並べること。
4. 簡潔に答えること。
5. コマンドやコードは ``` で囲んだコードブロックにし、```bash のように言語名を付けること。
   コードブロックの中にはSource IDを書かず、その直前の文の末尾に付けること。"""

ABSTAIN_ANSWER = (
    "研究室の知識ベースに、この質問に答えるための根拠が見つかりませんでした。"
    "キーワードを変えて検索するか、Outlineで直接探してください。"
)

# 1件の根拠としてLLMに渡す本文の上限（チャンク長+オーバーラップより十分大きい値）。
SOURCE_MAX_CHARS = 1500

_CITATION = re.compile(r"\[S(\d+)\]")


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class ChatModel(Protocol):
    def chat(self, messages: list[dict[str, str]]) -> str: ...


@dataclass(frozen=True)
class Source:
    id: str
    chunk: Chunk
    cited: bool


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    abstained: bool
    sources: list[Source]
    timings_ms: dict[str, int]


class EmbeddingError(RuntimeError):
    """質問のEmbedding取得に失敗した（検索基盤側の障害）。"""


class AIServiceError(RuntimeError):
    """RerankerまたはLLMが利用できない（AI系サービスの障害）。"""


def select_sources(chunks: list[Chunk], top_k: int, min_score: float) -> list[Chunk]:
    """Rerank済み（関連度降順）のchunksから、しきい値以上の上位top_k件を選ぶ。"""
    return [c for c in chunks if c.score >= min_score][:top_k]


def build_messages(question: str, sources: list[Chunk]) -> list[dict[str, str]]:
    blocks = []
    for i, chunk in enumerate(sources, start=1):
        text = chunk.text[:SOURCE_MAX_CHARS]
        blocks.append(f"[S{i}] タイトル: {chunk.title}\n{text}")
    context = "\n\n".join(blocks)
    user = f"# 資料\n\n{context}\n\n# 質問\n\n{question}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def extract_citations(answer: str, source_count: int) -> list[int]:
    """回答中の [Sn] を出現順・重複なしで返す（1始まり。範囲外の番号は無視する）。"""
    cited: list[int] = []
    for match in _CITATION.finditer(answer):
        n = int(match.group(1))
        if 1 <= n <= source_count and n not in cited:
            cited.append(n)
    return cited


def is_no_answer(answer: str) -> bool:
    """LLMが規則2に従い「資料からは分かりません。」と答えたか。"""
    return answer.strip().startswith(NO_ANSWER_TEXT.rstrip("。"))


class RagService:
    def __init__(
        self,
        search: SearchService,
        embedder: Embedder,
        reranker: Reranker,
        llm: ChatModel,
        candidates: int = 20,
        top_k: int = 5,
        min_score: float = 0.3,
    ) -> None:
        self._search = search
        self._embedder = embedder
        self._reranker = reranker
        self._llm = llm
        self._candidates = candidates
        self._top_k = top_k
        self._min_score = min_score

    def answer(self, question: str, top_k: int | None = None) -> RagAnswer:
        top_k = top_k or self._top_k
        timings: dict[str, int] = {}

        started = time.perf_counter()
        try:
            vectors = self._embedder.embed([question])
        except Exception as exc:
            raise EmbeddingError("embedding service error") from exc
        if not vectors:
            raise EmbeddingError("embedding service returned no vector")
        candidates = self._search.candidate_chunks(question, vectors[0], self._candidates)
        timings["search_ms"] = _elapsed_ms(started)

        started = time.perf_counter()
        try:
            ranked = rerank_chunks(question, candidates, self._reranker)
        except Exception as exc:
            raise AIServiceError("reranker error") from exc
        timings["rerank_ms"] = _elapsed_ms(started)

        selected = select_sources(ranked, top_k, self._min_score)
        if not selected:
            logger.info(
                "RAG: 根拠なしのため回答を控えます（候補%d件, 最高関連度%.3f）",
                len(ranked),
                ranked[0].score if ranked else 0.0,
            )
            timings["llm_ms"] = 0
            return RagAnswer(ABSTAIN_ANSWER, abstained=True, sources=[], timings_ms=timings)

        started = time.perf_counter()
        try:
            answer = self._llm.chat(build_messages(question, selected))
        except Exception as exc:
            raise AIServiceError("llm error") from exc
        timings["llm_ms"] = _elapsed_ms(started)

        cited = set(extract_citations(answer, len(selected)))
        sources = [
            Source(id=f"S{i}", chunk=chunk, cited=i in cited)
            for i, chunk in enumerate(selected, start=1)
        ]
        abstained = is_no_answer(answer)
        logger.info(
            "RAG: 根拠%d件（引用%d件）, abstained=%s, search=%dms rerank=%dms llm=%dms",
            len(selected),
            len(cited),
            abstained,
            timings["search_ms"],
            timings["rerank_ms"],
            timings["llm_ms"],
        )
        return RagAnswer(answer, abstained=abstained, sources=sources, timings_ms=timings)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
