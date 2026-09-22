"""chienami-apiへ質問を投げてRecall@k / MRRを計測するCLI。

使い方: python -m chienami_eval.runner <questions.yaml> [--base-url URL] [--k 1,3,5,10]
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import httpx
import yaml

from .metrics import EvalCase, EvalResult, build_result, mean_reciprocal_rank, recall_at_k


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
    cases: Sequence[EvalCase], base_url: str, max_k: int, timeout: float = 30.0
) -> list[EvalResult]:
    results: list[EvalResult] = []
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        for case in cases:
            resp = client.get("/search", params={"q": case.query, "limit": max_k})
            resp.raise_for_status()
            body = resp.json()
            urls = [r["url"] for r in body.get("results", [])]
            results.append(build_result(case, urls))
    return results


def print_report(results: Sequence[EvalResult], ks: Sequence[int]) -> None:
    print(f"評価対象: {len(results)}問")
    for r in results:
        if r.hit_ranks:
            print(f"  [HIT ] rank={min(r.hit_ranks)}  {r.case.query}")
        else:
            print(f"  [MISS] rank=-  {r.case.query}")
    print()
    for k in ks:
        print(f"Recall@{k}: {recall_at_k(list(results), k):.3f}")
    print(f"MRR: {mean_reciprocal_rank(list(results)):.3f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chienami Search 検索評価ツール")
    parser.add_argument("questions_file", help="質問セットYAMLファイルのパス")
    parser.add_argument("--base-url", default="http://api:8000", help="chienami-apiのベースURL")
    parser.add_argument("--k", default="1,3,5,10", help="カンマ区切りのRecall@k一覧")
    args = parser.parse_args(argv)

    ks = [int(x) for x in args.k.split(",")]
    max_k = max(ks)

    cases = load_cases(args.questions_file)
    if not cases:
        print("評価対象の質問がありません。questions.yamlを確認してください。", file=sys.stderr)
        return 1

    results = run(cases, args.base_url, max_k)
    print_report(results, ks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
