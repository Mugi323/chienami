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
