import httpx
import respx

from chienami_indexer.outline_client import OutlineClient


@respx.mock
def test_list_public_collections_filters_by_permission():
    respx.post("http://outline.test/api/collections.list").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "data": [
                    {"id": "c1", "name": "公開", "permission": "read"},
                    {"id": "c2", "name": "限定公開", "permission": None},
                    {"id": "c3", "name": "編集可", "permission": "read_write"},
                ],
                "pagination": {"offset": 0, "limit": 100},
            },
        )
    )

    with OutlineClient("http://outline.test", "token") as client:
        collections = client.list_public_collections()

    assert {c.id for c in collections} == {"c1", "c3"}


@respx.mock
def test_iter_published_documents_skips_archived_deleted_and_draft():
    respx.post("http://outline.test/api/documents.list").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "data": [
                    {
                        "id": "d1",
                        "collectionId": "c1",
                        "title": "公開済み",
                        "text": "本文",
                        "url": "/doc/d1",
                        "updatedAt": "2026-01-01T00:00:00Z",
                        "publishedAt": "2026-01-01T00:00:00Z",
                        "archivedAt": None,
                        "deletedAt": None,
                    },
                    {
                        "id": "d2",
                        "collectionId": "c1",
                        "title": "下書き",
                        "text": "未公開",
                        "url": "/doc/d2",
                        "updatedAt": "2026-01-01T00:00:00Z",
                        "publishedAt": None,
                        "archivedAt": None,
                        "deletedAt": None,
                    },
                    {
                        "id": "d3",
                        "collectionId": "c1",
                        "title": "アーカイブ済み",
                        "text": "本文",
                        "url": "/doc/d3",
                        "updatedAt": "2026-01-01T00:00:00Z",
                        "publishedAt": "2026-01-01T00:00:00Z",
                        "archivedAt": "2026-01-02T00:00:00Z",
                        "deletedAt": None,
                    },
                ],
                "pagination": {"offset": 0, "limit": 100},
            },
        )
    )

    with OutlineClient("http://outline.test", "token") as client:
        docs = list(client.iter_published_documents("c1"))

    assert [d.id for d in docs] == ["d1"]


@respx.mock
def test_not_ok_response_raises():
    respx.post("http://outline.test/api/collections.list").mock(
        return_value=httpx.Response(200, json={"ok": False, "error": "unauthorized"})
    )

    with OutlineClient("http://outline.test", "token") as client:
        try:
            client.list_public_collections()
        except RuntimeError as e:
            assert "unauthorized" in str(e)
        else:
            raise AssertionError("expected RuntimeError")
