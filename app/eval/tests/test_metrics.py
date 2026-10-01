from chienami_eval.metrics import (
    EvalCase,
    build_result,
    is_hit_at_k,
    mean_reciprocal_rank,
    recall_at_k,
    reciprocal_rank,
)


def _case(expected_urls):
    return EvalCase(query="q", expected_urls=tuple(expected_urls))


def test_build_result_records_hit_rank():
    case = _case(["https://x/doc/a"])
    result = build_result(case, ["https://x/doc/z", "https://x/doc/a", "https://x/doc/b"])
    assert result.hit_ranks == (2,)


def test_build_result_no_hit():
    case = _case(["https://x/doc/a"])
    result = build_result(case, ["https://x/doc/z", "https://x/doc/b"])
    assert result.hit_ranks == ()


def test_build_result_multiple_expected_urls_any_match():
    case = _case(["https://x/doc/a", "https://x/doc/b"])
    result = build_result(case, ["https://x/doc/z", "https://x/doc/b", "https://x/doc/a"])
    assert result.hit_ranks == (2, 3)


def test_is_hit_at_k():
    case = _case(["https://x/doc/a"])
    result = build_result(case, ["https://x/doc/z", "https://x/doc/a"])
    assert is_hit_at_k(result, 1) is False
    assert is_hit_at_k(result, 2) is True
    assert is_hit_at_k(result, 10) is True


def test_recall_at_k_aggregates_over_results():
    case = _case(["https://x/doc/a"])
    hit = build_result(case, ["https://x/doc/a"])  # rank 1
    miss = build_result(case, ["https://x/doc/z"])  # no hit
    assert recall_at_k([hit, miss], 1) == 0.5
    assert recall_at_k([], 1) == 0.0


def test_reciprocal_rank():
    case = _case(["https://x/doc/a"])
    hit_rank2 = build_result(case, ["https://x/doc/z", "https://x/doc/a"])
    miss = build_result(case, ["https://x/doc/z"])
    assert reciprocal_rank(hit_rank2) == 0.5
    assert reciprocal_rank(miss) == 0.0


def test_mean_reciprocal_rank():
    case = _case(["https://x/doc/a"])
    hit_rank1 = build_result(case, ["https://x/doc/a"])
    hit_rank2 = build_result(case, ["https://x/doc/z", "https://x/doc/a"])
    assert mean_reciprocal_rank([hit_rank1, hit_rank2]) == (1.0 + 0.5) / 2
    assert mean_reciprocal_rank([]) == 0.0


# --- 答えのない質問・RAG評価（Phase 4） ---

from chienami_eval.metrics import (  # noqa: E402
    answerable,
    build_rag_result,
    summarize_rag,
)


def test_answerable():
    assert answerable(_case(["https://x/doc/a"]))
    assert not answerable(_case([]))


def _source(url, cited):
    return {"id": "S1", "url": url, "cited": cited}


def test_build_rag_result_collects_sources_cited_and_time():
    body = {
        "answer": "a",
        "abstained": False,
        "sources": [_source("https://x/doc/a", True), _source("https://x/doc/b", False)],
        "timings": {"search_ms": 10, "rerank_ms": 20, "llm_ms": 70},
    }
    r = build_rag_result(_case(["https://x/doc/a"]), body)
    assert r.abstained is False
    assert r.source_urls == ("https://x/doc/a", "https://x/doc/b")
    assert r.cited_urls == ("https://x/doc/a",)
    assert r.total_ms == 100


def test_build_rag_result_abstained_without_sources():
    r = build_rag_result(_case([]), {"answer": "a", "abstained": True, "sources": []})
    assert r.abstained and r.source_urls == () and r.total_ms == 0


def test_summarize_rag():
    a = "https://x/doc/a"
    results = [
        # 正解を引用して回答
        build_rag_result(_case([a]), {"abstained": False, "sources": [_source(a, True)]}),
        # 正解は根拠に入ったが引用せず
        build_rag_result(_case([a]), {"abstained": False, "sources": [_source(a, False)]}),
        # 答えのある質問なのに控えた
        build_rag_result(_case([a]), {"abstained": True, "sources": []}),
        # 答えのない質問で正しく控えた
        build_rag_result(
            _case([]), {"abstained": True, "sources": [], "timings": {"search_ms": 400}}
        ),
    ]
    s = summarize_rag(results)
    assert s.answerable_count == 3
    assert s.answered_rate == 2 / 3
    assert s.source_hit_rate == 2 / 3
    assert s.cited_hit_rate == 1 / 3
    assert s.unanswerable_count == 1
    assert s.abstain_rate_unanswerable == 1.0
    assert s.mean_total_ms == 100


def test_summarize_rag_empty():
    s = summarize_rag([])
    assert s.answerable_count == 0 and s.answered_rate == 0.0 and s.mean_total_ms == 0.0
