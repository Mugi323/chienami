import json
from datetime import UTC, datetime

import httpx
import pytest

from chienami_api.invitations import AuthentikInvitationClient

NOW = datetime(2026, 10, 15, 3, 0, tzinfo=UTC)
FLOW_PK = "11111111-1111-1111-1111-111111111111"


def _invitation(pk, expires, single_use=False):
    return {"pk": pk, "expires": expires, "single_use": single_use}


def _client(handler):
    client = AuthentikInvitationClient(
        "http://authentik", "token", "https://auth.lab.local/", "chienami-invite-enrollment"
    )
    client._client = httpx.Client(
        base_url="http://authentik/api/v3", transport=httpx.MockTransport(handler)
    )
    return client


def test_create_posts_invitation_for_enrollment_flow():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v3/flows/instances/":
            assert request.url.params["slug"] == "chienami-invite-enrollment"
            return httpx.Response(200, json={"results": [{"pk": FLOW_PK}]})
        body = json.loads(request.content)
        assert body["flow"] == FLOW_PK
        assert body["expires"] == "2026-10-22T03:00:00+00:00"
        assert body["single_use"] is True
        assert body["name"].startswith("chienami-20261015-030000-")
        return httpx.Response(201, json=_invitation("abc", body["expires"], True))

    invitation = _client(handler).create(7, True, now=NOW)

    assert invitation.id == "abc"
    assert invitation.url == "https://auth.lab.local/if/flow/chienami-invite-enrollment/?itoken=abc"
    assert invitation.expires == datetime(2026, 10, 22, 3, 0, tzinfo=UTC)
    assert invitation.single_use is True
    assert [r.method for r in requests] == ["GET", "POST"]


def test_create_raises_when_flow_is_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    with pytest.raises(RuntimeError):
        _client(handler).create(7, False, now=NOW)


def test_list_active_skips_expired_and_follows_pages():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["flow__slug"] == "chienami-invite-enrollment"
        if request.url.params["page"] == "1":
            return httpx.Response(
                200,
                json={
                    "pagination": {"next": 2},
                    "results": [_invitation("a", "2026-11-01T00:00:00Z")],
                },
            )
        return httpx.Response(
            200,
            json={
                "pagination": {"next": 0},
                "results": [
                    _invitation("b", "2026-10-14T00:00:00Z"),
                    _invitation("c", None),
                ],
            },
        )

    assert [i.id for i in _client(handler).list_active(now=NOW)] == ["a"]


def test_delete_returns_false_when_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        return httpx.Response(404 if request.url.path.endswith("/missing/") else 204)

    client = _client(handler)
    assert client.delete("abc") is True
    assert client.delete("missing") is False
