import httpx

from chienami_api.points import (
    AuthoredDocument,
    OutlineDocumentSource,
    PointRules,
    PointsService,
    compute_points,
)

RULES = PointRules(points_per_document=10, characters_per_point=100)


def _doc(author_id, name, characters):
    return AuthoredDocument(author_id=author_id, author_name=name, characters=characters)


def test_compute_points_sums_per_author_and_sorts_desc():
    users = compute_points(
        [_doc("u1", "佐藤", 250), _doc("u2", "鈴木", 1000), _doc("u1", "佐藤", 50)], RULES
    )
    # u1: (10 + 2) + (10 + 0) = 22, u2: 10 + 10 = 20
    assert [(u.rank, u.user_id, u.points) for u in users] == [(1, "u1", 22), (2, "u2", 20)]
    assert users[0].documents == 2 and users[0].characters == 300


def test_compute_points_floors_characters_per_document():
    # 99文字×2件は文書ごとに切り捨てるので文字量点は0（合算198文字でも1点にならない）。
    users = compute_points([_doc("u1", "a", 99), _doc("u1", "a", 99)], RULES)
    assert users[0].points == 20


def test_compute_points_gives_same_rank_on_tie():
    users = compute_points([_doc("u1", "a", 0), _doc("u2", "b", 0), _doc("u3", "c", 500)], RULES)
    assert [(u.rank, u.user_id) for u in users] == [(1, "u3"), (2, "u1"), (2, "u2")]


def test_compute_points_empty():
    assert compute_points([], RULES) == []


class _FakeSource:
    def __init__(self):
        self.calls = 0

    def iter_documents(self):
        self.calls += 1
        return [_doc("u1", "a", 100)]


def test_points_service_caches_until_ttl():
    now = [1000.0]
    source = _FakeSource()
    service = PointsService(source, RULES, cache_seconds=300, clock=lambda: now[0])

    updated_at, users = service.ranking()
    assert (updated_at, users[0].points) == (1000.0, 11)
    now[0] += 299
    service.ranking()
    assert source.calls == 1
    now[0] += 1
    assert service.ranking()[0] == 1300.0
    assert source.calls == 2


def _outline_handler(request: httpx.Request) -> httpx.Response:
    import json

    payload = json.loads(request.content)
    if request.url.path == "/api/collections.list":
        data = [
            {"id": "c-public", "permission": "read"},
            {"id": "c-private", "permission": None},
        ]
    elif payload["collectionId"] == "c-public":
        data = [
            {"publishedAt": "x", "createdBy": {"id": "u1", "name": "佐藤"}, "text": " 本文 "},
            {"publishedAt": None, "createdBy": {"id": "u1", "name": "佐藤"}, "text": "下書き"},
            {"publishedAt": "x", "archivedAt": "y", "createdBy": {"id": "u2"}, "text": "a"},
            {"publishedAt": "x", "createdBy": None, "text": "作成者不明"},
        ]
    else:
        raise AssertionError("非公開Collectionの文書を取得してはいけない")
    return httpx.Response(200, json={"ok": True, "data": data})


def test_outline_source_reads_only_published_docs_in_public_collections():
    source = OutlineDocumentSource("http://outline", "token")
    source._client = httpx.Client(
        base_url="http://outline", transport=httpx.MockTransport(_outline_handler)
    )
    assert list(source.iter_documents()) == [_doc("u1", "佐藤", 2)]
