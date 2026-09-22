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
