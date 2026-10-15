"""招待リンクの発行・一覧・削除（Issue #81）。

AuthentikのInvitation APIを、招待制セルフ登録フロー（研究室メンバー登録,
app/authentik/blueprints/enrollment-invite-name-password.yaml）に限定して呼び出す。
トークンは招待の作成・閲覧・削除だけを許すサービスアカウントのもの
（app/authentik/blueprints/invite-admin.yaml）で、管理者権限は持たせない。

誰が発行ページを使えるか（ログイン済みの全員）はAPIではなく、Caddyのforward_authと
Authentik側のポリシーで判定する。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx


@dataclass(frozen=True)
class Invitation:
    id: str
    url: str
    expires: datetime
    single_use: bool


class AuthentikInvitationClient:
    def __init__(
        self,
        api_url: str,
        api_token: str,
        public_url: str,
        flow_slug: str,
        timeout: float = 10.0,
    ) -> None:
        self._client = httpx.Client(
            base_url=f"{api_url.rstrip('/')}/api/v3",
            headers={"Authorization": f"Bearer {api_token}", "Accept": "application/json"},
            timeout=timeout,
        )
        self._public_url = public_url.rstrip("/")
        self._flow_slug = flow_slug
        self._flow_pk: str | None = None

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        resp = self._client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp

    def _flow(self) -> str:
        if self._flow_pk is None:
            results = self._request(
                "GET", "/flows/instances/", params={"slug": self._flow_slug}
            ).json()["results"]
            if not results:
                raise RuntimeError(f"Authentik flow not found: {self._flow_slug}")
            self._flow_pk = results[0]["pk"]
        return self._flow_pk

    def _to_invitation(self, data: dict) -> Invitation:
        return Invitation(
            id=data["pk"],
            url=f"{self._public_url}/if/flow/{self._flow_slug}/?itoken={data['pk']}",
            expires=datetime.fromisoformat(data["expires"]),
            single_use=data["single_use"],
        )

    def create(self, valid_days: int, single_use: bool, now: datetime | None = None) -> Invitation:
        now = now or datetime.now(UTC)
        payload = {
            # Invitation.name はslug（英数字・-・_）のみ許されるため、日時とランダム値で一意にする。
            "name": f"chienami-{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}",
            "expires": (now + timedelta(days=valid_days)).isoformat(),
            "single_use": single_use,
            "flow": self._flow(),
            "fixed_data": {},
        }
        return self._to_invitation(
            self._request("POST", "/stages/invitation/invitations/", json=payload).json()
        )

    def list_active(self, now: datetime | None = None) -> list[Invitation]:
        """期限内の招待を有効期限の遅い順に返す（期限切れはAuthentikが後で自動削除する）。"""
        now = now or datetime.now(UTC)
        invitations: list[Invitation] = []
        page = 1
        while True:
            body = self._request(
                "GET",
                "/stages/invitation/invitations/",
                params={
                    "flow__slug": self._flow_slug,
                    "ordering": "-expires",
                    "page": page,
                    "page_size": 100,
                },
            ).json()
            invitations.extend(self._to_invitation(d) for d in body["results"] if d.get("expires"))
            if not body["pagination"].get("next"):
                break
            page += 1
        return [i for i in invitations if i.expires > now]

    def delete(self, invitation_id: str) -> bool:
        """招待を削除する。存在しなければFalse。"""
        resp = self._client.delete(f"/stages/invitation/invitations/{invitation_id}/")
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        return True
