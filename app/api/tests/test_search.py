from types import SimpleNamespace

from chienami_api.search import dedupe_by_document


def _hit(document_id: str, score: float, chunk_index: int = 0, title: str = "title"):
    return SimpleNamespace(
        score=score,
        payload={
            "document_id": document_id,
            "title": title,
            "url": f"https://knowledge.lab.local/doc/{document_id}",
            "text": f"snippet for {document_id}#{chunk_index}",
            "chunk_index": chunk_index,
        },
    )


def test_dedupe_keeps_highest_score_per_document():
    hits = [
        _hit("d1", score=0.9, chunk_index=0),
        _hit("d1", score=0.5, chunk_index=1),
        _hit("d2", score=0.8, chunk_index=0),
    ]
    results = dedupe_by_document(hits, limit=10)
    assert [r.document_id for r in results] == ["d1", "d2"]
    assert results[0].score == 0.9


def test_dedupe_respects_limit():
    hits = [_hit(f"d{i}", score=1.0 - i * 0.01) for i in range(20)]
    results = dedupe_by_document(hits, limit=5)
    assert len(results) == 5
    assert [r.document_id for r in results] == [f"d{i}" for i in range(5)]


def test_dedupe_skips_hits_without_document_id():
    hits = [
        SimpleNamespace(score=0.9, payload={}),
        _hit("d1", score=0.8),
    ]
    results = dedupe_by_document(hits, limit=10)
    assert [r.document_id for r in results] == ["d1"]


def test_dedupe_handles_empty_hits():
    assert dedupe_by_document([], limit=10) == []


# --- Hybrid検索（Phase 4） ---

from chienami_api.search import (  # noqa: E402
    Chunk,
    SearchService,
    extract_keywords,
    keyword_score,
    rerank_chunks,
    rrf_fuse,
)


def _chunk(document_id: str, chunk_index: int = 0, text: str = "", score: float = 0.0) -> Chunk:
    return Chunk(
        document_id=document_id,
        title=f"title {document_id}",
        url=f"https://knowledge.lab.local/doc/{document_id}",
        chunk_index=chunk_index,
        text=text or f"text {document_id}#{chunk_index}",
        score=score,
    )


class _FakeReranker:
    def __init__(self, ranked):
        self.ranked = ranked
        self.calls = []

    def rerank(self, query, texts):
        self.calls.append((query, texts))
        return self.ranked


class _FakeQdrant:
    def __init__(self, dense_points=(), scroll_points=()):
        self.dense_points = list(dense_points)
        self.scroll_points = list(scroll_points)
        self.scroll_filter = None

    def query_points(self, **kwargs):
        return SimpleNamespace(points=self.dense_points[: kwargs["limit"]])

    def scroll(self, **kwargs):
        self.scroll_filter = kwargs["scroll_filter"]
        return self.scroll_points, None


def _point(document_id: str, chunk_index: int, text: str, score: float = 0.0):
    return SimpleNamespace(
        score=score,
        payload={
            "document_id": document_id,
            "title": f"title {document_id}",
            "url": f"https://knowledge.lab.local/doc/{document_id}",
            "chunk_index": chunk_index,
            "text": text,
        },
    )


def test_extract_keywords_picks_kanji_katakana_and_alnum():
    query = "PCRのアニーリング温度は何度にすればいい？"
    assert extract_keywords(query) == ["PCR", "アニーリング", "温度", "何度"]


def test_extract_keywords_skips_hiragana_and_single_chars_and_dedupes():
    assert extract_keywords("これはなに？") == []
    assert extract_keywords("a と 本") == []
    assert extract_keywords("PCR と pcr と PCR") == ["PCR"]


def test_extract_keywords_keeps_model_numbers():
    assert extract_keywords("TaKaRa Ex-Taq と RTX-3090 の設定") == [
        "TaKaRa",
        "Ex-Taq",
        "RTX-3090",
        "設定",
    ]


def test_extract_keywords_caps_count():
    query = " ".join(f"KW{i}" for i in range(20))
    assert len(extract_keywords(query)) == 8


def test_keyword_score_counts_distinct_keywords_case_insensitive():
    assert keyword_score("pcrのアニーリング温度は58度", ["PCR", "温度", "遠心"]) == 2


def test_rrf_fuse_merges_same_chunk_and_ranks_by_combined_score():
    dense = [_chunk("a"), _chunk("b"), _chunk("c")]
    keyword = [_chunk("c"), _chunk("d")]
    fused = rrf_fuse([dense, keyword], k=60)
    keys = [c.document_id for c in fused]
    # cは両方に出るため最上位、残りはDenseの1位→2位→Keywordの2位の順。
    assert keys == ["c", "a", "b", "d"]
    assert fused[0].score == 1 / 63 + 1 / 61


def test_rrf_fuse_distinguishes_chunks_of_same_document():
    fused = rrf_fuse([[_chunk("a", 0), _chunk("a", 1)]])
    assert [c.chunk_index for c in fused] == [0, 1]


def test_rerank_chunks_reorders_and_replaces_score():
    chunks = [_chunk("a"), _chunk("b"), _chunk("c")]
    reranker = _FakeReranker([(2, 0.9), (0, 0.4), (1, 0.01)])
    ranked = rerank_chunks("質問", chunks, reranker)
    assert [c.document_id for c in ranked] == ["c", "a", "b"]
    assert [c.score for c in ranked] == [0.9, 0.4, 0.01]
    assert reranker.calls == [("質問", [c.text for c in chunks])]


def test_rerank_chunks_skips_call_for_empty_input():
    reranker = _FakeReranker([])
    assert rerank_chunks("質問", [], reranker) == []
    assert reranker.calls == []


def test_keyword_chunks_ranks_by_number_of_matched_keywords():
    qdrant = _FakeQdrant(
        scroll_points=[
            _point("a", 0, "温度だけ"),
            _point("b", 0, "PCRのアニーリング温度"),
            _point("c", 0, "どれも含まない"),
            SimpleNamespace(payload={}),
        ]
    )
    service = SearchService(qdrant, "col")
    chunks = service.keyword_chunks(["PCR", "温度"], limit=10)
    assert [(c.document_id, c.score) for c in chunks] == [("b", 2.0), ("a", 1.0)]
    assert len(qdrant.scroll_filter.should) == 2


def test_keyword_chunks_without_keywords_does_not_query():
    qdrant = _FakeQdrant()
    assert SearchService(qdrant, "col").keyword_chunks([], limit=10) == []
    assert qdrant.scroll_filter is None


def test_hybrid_chunks_fuses_dense_and_keyword_then_reranks():
    qdrant = _FakeQdrant(
        dense_points=[_point("a", 0, "意味が近い文", 0.9), _point("b", 0, "PCRの話", 0.8)],
        scroll_points=[_point("b", 0, "PCRの話"), _point("c", 0, "PCR装置")],
    )
    reranker = _FakeReranker([(2, 0.95), (0, 0.5), (1, 0.1)])
    chunks = SearchService(qdrant, "col").hybrid_chunks(
        "PCRについて", [0.1], candidates=10, reranker=reranker
    )
    # RRF順は b(両方), a, c。rerankの結果 c, b, a の順になる。
    assert [c.document_id for c in chunks] == ["c", "b", "a"]
    assert [c.score for c in chunks] == [0.95, 0.5, 0.1]


def test_hybrid_chunks_falls_back_to_rrf_order_when_reranker_fails():
    class _Broken:
        def rerank(self, query, texts):
            raise RuntimeError("reranker down")

    qdrant = _FakeQdrant(
        dense_points=[_point("a", 0, "x", 0.9)], scroll_points=[_point("b", 0, "PCR")]
    )
    chunks = SearchService(qdrant, "col").hybrid_chunks(
        "PCR", [0.1], candidates=10, reranker=_Broken()
    )
    assert [c.document_id for c in chunks] == ["a", "b"]


def test_hybrid_chunks_limits_candidates_passed_to_reranker():
    qdrant = _FakeQdrant(dense_points=[_point(f"d{i}", 0, "x", 1 - i / 100) for i in range(30)])
    reranker = _FakeReranker([])
    SearchService(qdrant, "col").hybrid_chunks("それは", [0.1], candidates=5, reranker=reranker)
    assert len(reranker.calls[0][1]) == 5
