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
