"""検索評価用の指標計算（design書11章: Phase 3/4 検索・RAG評価セット）。

評価は「LLMの文章の上手さ」ではなく「必要な根拠文書（URL）を取得できたか」で行う。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    query: str
    expected_urls: tuple[str, ...]


@dataclass(frozen=True)
class EvalResult:
    case: EvalCase
    # 正解URLが検索結果内に現れた順位（1-based）の一覧。見つからなければ空。
    hit_ranks: tuple[int, ...]


def build_result(case: EvalCase, result_urls: list[str]) -> EvalResult:
    expected = set(case.expected_urls)
    hit_ranks = tuple(rank for rank, url in enumerate(result_urls, start=1) if url in expected)
    return EvalResult(case=case, hit_ranks=hit_ranks)


def is_hit_at_k(result: EvalResult, k: int) -> bool:
    return any(rank <= k for rank in result.hit_ranks)


def recall_at_k(results: list[EvalResult], k: int) -> float:
    if not results:
        return 0.0
    hits = sum(1 for r in results if is_hit_at_k(r, k))
    return hits / len(results)


def reciprocal_rank(result: EvalResult) -> float:
    if not result.hit_ranks:
        return 0.0
    return 1.0 / min(result.hit_ranks)


def mean_reciprocal_rank(results: list[EvalResult]) -> float:
    if not results:
        return 0.0
    return sum(reciprocal_rank(r) for r in results) / len(results)


def answerable(case: EvalCase) -> bool:
    """正解文書が指定された質問か。expected_urls が空の質問は「知識ベースに答えがない質問」
    として扱い、検索のRecall/MRRには含めず、RAGでは回答を控えたかを評価する。"""
    return bool(case.expected_urls)


# --- RAG（/chat, Phase 4）の評価 ---


@dataclass(frozen=True)
class RagResult:
    case: EvalCase
    abstained: bool
    # LLMに渡された根拠（sources）のURLと、そのうち回答で引用されたもののURL。
    source_urls: tuple[str, ...]
    cited_urls: tuple[str, ...]
    total_ms: int


@dataclass(frozen=True)
class RagSummary:
    answerable_count: int
    # 以下3つは答えのある質問に対する割合。
    answered_rate: float  # 回答を控えなかった割合
    source_hit_rate: float  # 正解文書が根拠に含まれた割合
    cited_hit_rate: float  # 正解文書が回答で引用された割合
    unanswerable_count: int
    abstain_rate_unanswerable: float  # 答えのない質問で回答を控えた割合
    mean_total_ms: float


def build_rag_result(case: EvalCase, body: dict) -> RagResult:
    sources = body.get("sources", [])
    return RagResult(
        case=case,
        abstained=bool(body.get("abstained")),
        source_urls=tuple(s["url"] for s in sources),
        cited_urls=tuple(s["url"] for s in sources if s.get("cited")),
        total_ms=sum((body.get("timings") or {}).values()),
    )


def _contains_expected(urls: tuple[str, ...], case: EvalCase) -> bool:
    return bool(set(urls) & set(case.expected_urls))


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def summarize_rag(results: list[RagResult]) -> RagSummary:
    ans = [r for r in results if answerable(r.case)]
    unans = [r for r in results if not answerable(r.case)]
    return RagSummary(
        answerable_count=len(ans),
        answered_rate=_rate(sum(1 for r in ans if not r.abstained), len(ans)),
        source_hit_rate=_rate(
            sum(1 for r in ans if _contains_expected(r.source_urls, r.case)), len(ans)
        ),
        cited_hit_rate=_rate(
            sum(1 for r in ans if _contains_expected(r.cited_urls, r.case)), len(ans)
        ),
        unanswerable_count=len(unans),
        abstain_rate_unanswerable=_rate(sum(1 for r in unans if r.abstained), len(unans)),
        mean_total_ms=_rate(sum(r.total_ms for r in results), len(results)),
    )
