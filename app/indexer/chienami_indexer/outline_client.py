"""Outline APIクライアント（索引化に必要な最小限のRPC呼び出しのみ実装）。

Outline API は https://app.getoutline.com/developers に準拠するRPCスタイル
（`POST /api/<method>`, レスポンスは `{ok, status, data, pagination}`）。
`collectionId` / `statusFilter` は上流では非推奨だが、自己ホスト版（1.10.0系）
との互換性を優先しあえて使用する。公開判定（archivedAt/deletedAt/publishedAt）は
クライアント側で再フィルタし、APIバージョン差異に依存しないようにする。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import httpx

# design書7.3節: 権限連携が完成するまでは、Collectionのデフォルト権限が
# 設定されている（＝ワークスペース全員に見える）ものだけを索引対象にする。
# Outline APIはこの状態を permission: "read" | "read_write" で表し、
# 招待制/グループ限定のCollectionは permission: null を返す。
PUBLIC_PERMISSIONS = {"read", "read_write"}


@dataclass(frozen=True)
class OutlineCollection:
    id: str
    name: str
    permission: str | None


@dataclass(frozen=True)
class OutlineDocument:
    id: str
    collection_id: str
    title: str
    text: str
    url: str
    updated_at: str


class OutlineClient:
    def __init__(self, base_url: str, api_token: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                # indexerはReverse Proxy（Caddy）を経由せずDocker内部ネットワークで
                # 直接Outlineへアクセスする。FORCE_HTTPS=true の場合、Outlineは
                # X-Forwarded-Proto が無いリクエストを「安全でない」と判定しAPI
                # ルーターへ到達させない（405 Method Not Allowedになる、Issue #44）。
                # ブラウザ経由の場合はCaddyがこのヘッダーを自動付与するため発生しない。
                "X-Forwarded-Proto": "https",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OutlineClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _post(self, method: str, payload: dict) -> dict:
        resp = self._client.post(f"/api/{method}", json=payload)
        resp.raise_for_status()
        body = resp.json()
        if not body.get("ok", False):
            raise RuntimeError(f"Outline API {method} failed: {body}")
        return body

    def list_public_collections(self) -> list[OutlineCollection]:
        collections: list[OutlineCollection] = []
        offset = 0
        limit = 100
        while True:
            body = self._post("collections.list", {"offset": offset, "limit": limit})
            data = body.get("data", [])
            for item in data:
                permission = item.get("permission")
                if permission in PUBLIC_PERMISSIONS:
                    collections.append(
                        OutlineCollection(
                            id=item["id"], name=item.get("name", ""), permission=permission
                        )
                    )
            if len(data) < limit:
                break
            offset += limit
        return collections

    def iter_published_documents(self, collection_id: str) -> Iterator[OutlineDocument]:
        offset = 0
        limit = 100
        while True:
            body = self._post(
                "documents.list",
                {"collectionId": collection_id, "offset": offset, "limit": limit},
            )
            data = body.get("data", [])
            for item in data:
                if item.get("archivedAt") or item.get("deletedAt"):
                    continue
                if not item.get("publishedAt"):
                    continue
                yield OutlineDocument(
                    id=item["id"],
                    collection_id=item.get("collectionId", collection_id),
                    title=item.get("title", ""),
                    text=item.get("text", ""),
                    url=item.get("url", ""),
                    updated_at=item.get("updatedAt", ""),
                )
            if len(data) < limit:
                break
            offset += limit
