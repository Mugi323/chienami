"""chienami-apiへ質問を投げて、検索（Recall@k / MRR）とRAG回答を評価するCLI。

使い方:
  python -m chienami_eval.runner <questions.yaml> [--base-url URL] [--k 1,3,5,10]
                                 [--mode semantic,hybrid] [--rag]

--mode に複数の検索方式を指定すると、方式ごとの結果を並べて比較できる（Phase 4）。
--rag を付けると、/chat の回答（根拠の取得・引用・回答を控えたか）も評価する。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import httpx
import yaml

from .metrics import (
    EvalCase,
    EvalResult,
    RagResult,
    answerable,
    build_rag_result,
    build_result,
    mean_reciprocal_rank,
    recall_at_k,
    summarize_rag,
)

SEARCH_MODES = ("semantic", "hybrid")


def load_cases(path: str) -> list[EvalCase]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    cases: list[EvalCase] = []
    for raw in data.get("cases", []):
        cases.append(
            EvalCase(
                query=raw["query"],
                expected_urls=tuple(raw.get("expected_urls", [])),
            )
        )
    return cases


def run(
    cases: Sequence[EvalCase],
    base_url: str,
    max_k: int,
    timeout: float = 30.0,
    mode: str = "semantic",
) -> list[EvalResult]:
    """答えのある質問（expected_urlsあり）だけを /search に投げて評価する。"""
    results: list[EvalResult] = []
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        for case in cases:
            if not answerable(case):
                continue
            resp = client.get("/search", params={"q": case.query, "limit": max_k, "mode": mode})
            resp.raise_for_status()
            body = resp.json()
            urls = [r["url"] for r in body.get("results", [])]
            results.append(build_result(case, urls))
    return results


def run_rag(cases: Sequence[EvalCase], base_url: str, timeout: float = 180.0) -> list[RagResult]:
    """全質問を /chat に投げて評価する（LLMの生成を待つためタイムアウトは長め）。"""
    results: list[RagResult] = []
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        for case in cases:
            resp = client.post("/chat", json={"question": case.query})
            resp.raise_for_status()
            results.append(build_rag_result(case, resp.json()))
    return results


def print_report(results: Sequence[EvalResult], ks: Sequence[int], mode: str = "semantic") -> None:
    print(f"[検索: {mode}] 評価対象: {len(results)}問")
    for r in results:
        if r.hit_ranks:
            print(f"  [HIT ] rank={min(r.hit_ranks)}  {r.case.query}")
        else:
            print(f"  [MISS] rank=-  {r.case.query}")
    print()
    for k in ks:
        print(f"Recall@{k}: {recall_at_k(list(results), k):.3f}")
    print(f"MRR: {mean_reciprocal_rank(list(results)):.3f}")


def print_comparison(results_by_mode: dict[str, list[EvalResult]], ks: Sequence[int]) -> None:
    modes = list(results_by_mode)
    print("[検索方式の比較]")
    print("指標".ljust(12) + "".join(m.rjust(10) for m in modes))
    for k in ks:
        row = "".join(f"{recall_at_k(results_by_mode[m], k):10.3f}" for m in modes)
        print(f"Recall@{k}".ljust(12) + row)
    row = "".join(f"{mean_reciprocal_rank(results_by_mode[m]):10.3f}" for m in modes)
    print("MRR".ljust(12) + row)


def print_rag_report(results: Sequence[RagResult]) -> None:
    summary = summarize_rag(list(results))
    print(f"[RAG回答] 評価対象: {len(results)}問")
    for r in results:
        if answerable(r.case):
            if r.abstained:
                label = "控えた"
            elif set(r.cited_urls) & set(r.case.expected_urls):
                label = "引用OK"
            elif set(r.source_urls) & set(r.case.expected_urls):
                label = "未引用"
            else:
                label = "根拠MISS"
        else:
            label = "控えた" if r.abstained else "回答した!"
        print(f"  [{label}] {r.total_ms / 1000:.1f}s  {r.case.query}")
    print()
    print(f"答えのある質問: {summary.answerable_count}問")
    print(f"  回答した割合:           {summary.answered_rate:.3f}")
    print(f"  正解文書が根拠に入った: {summary.source_hit_rate:.3f}")
    print(f"  正解文書を引用した:     {summary.cited_hit_rate:.3f}")
    print(f"答えのない質問: {summary.unanswerable_count}問")
    print(f"  回答を控えた割合:       {summary.abstain_rate_unanswerable:.3f}")
    print(f"平均回答時間: {summary.mean_total_ms / 1000:.1f}秒")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chienami Search 検索・RAG評価ツール")
    parser.add_argument("questions_file", help="質問セットYAMLファイルのパス")
    parser.add_argument("--base-url", default="http://api:8000", help="chienami-apiのベースURL")
    parser.add_argument("--k", default="1,3,5,10", help="カンマ区切りのRecall@k一覧")
    parser.add_argument(
        "--mode",
        default="semantic",
        help="カンマ区切りの検索方式（semantic, hybrid）。複数指定すると比較表を出す",
    )
    parser.add_argument("--rag", action="store_true", help="/chat のRAG回答も評価する")
    args = parser.parse_args(argv)

    ks = [int(x) for x in args.k.split(",")]
    max_k = max(ks)
    modes = [m.strip() for m in args.mode.split(",") if m.strip()]
    unknown = [m for m in modes if m not in SEARCH_MODES]
    if unknown:
        parser.error(f"不明な検索方式です: {', '.join(unknown)}（{', '.join(SEARCH_MODES)}）")

    cases = load_cases(args.questions_file)
    if not cases:
        print("評価対象の質問がありません。questions.yamlを確認してください。", file=sys.stderr)
        return 1

    results_by_mode: dict[str, list[EvalResult]] = {}
    for mode in modes:
        results_by_mode[mode] = run(cases, args.base_url, max_k, mode=mode)
        print_report(results_by_mode[mode], ks, mode=mode)
        print()
    if len(modes) > 1:
        print_comparison(results_by_mode, ks)
        print()

    if args.rag:
        print_rag_report(run_rag(cases, args.base_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
