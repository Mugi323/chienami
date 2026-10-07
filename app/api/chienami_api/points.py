"""文書作成量に応じた貢献ポイント（Issue #77）。

Outlineの「全員閲覧可Collection」の公開済み文書を作成者ごとに集計し、
「公開文書1件あたりの基本点 + 本文の文字量に応じた加点」でポイントを算出する。
ポイントはOutlineから毎回再計算できる派生値とし、専用のDBは持たない
（知識の正本はOutline, design書の方針）。

集計対象をindexerと同じ全員閲覧可Collectionに限るのは、招待制Collectionの
文書タイトル・作成者がランキング経由で漏れないようにするため（design書7.3節）。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

import httpx

# indexer（chienami_indexer/outline_client.py）と同じ判定。
PUBLIC_PERMISSIONS = {"read", "read_write"}


@dataclass(frozen=True)
class AuthoredDocument:
    author_id: str
    author_name: str
    characters: int


@dataclass(frozen=True)
class PointRules:
    # 公開文書1件あたりの基本点。
    points_per_document: int
    # この文字数ごとに1点を加点する。
    characters_per_point: int


@dataclass(frozen=True)
class UserPoints:
    rank: int
    user_id: str
    name: str
    documents: int
    characters: int
    points: int


class OutlineDocumentSource:
    """ポイント集計に必要な文書（作成者・本文の文字数）だけをOutline APIから取得する。"""

    def __init__(self, base_url: str, api_token: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                # Docker内部ネットワークから直接Outlineへアクセスするため、FORCE_HTTPS=true
                # でもAPIルーターへ到達できるよう付与する（Issue #44, indexerと同じ理由）。
                "X-Forwarded-Proto": "https",
            },
            timeout=timeout,
        )

    def _post(self, method: str, payload: dict) -> dict:
        resp = self._client.post(f"/api/{method}", json=payload)
        resp.raise_for_status()
        body = resp.json()
        if not body.get("ok", False):
            raise RuntimeError(f"Outline API {method} failed: {body}")
        return body

    def _paginate(self, method: str, payload: dict) -> Iterator[dict]:
        offset = 0
        limit = 100
        while True:
            data = self._post(method, {**payload, "offset": offset, "limit": limit}).get("data", [])
            yield from data
            if len(data) < limit:
                break
            offset += limit

    def iter_documents(self) -> Iterator[AuthoredDocument]:
        for collection in self._paginate("collections.list", {}):
            if collection.get("permission") not in PUBLIC_PERMISSIONS:
                continue
            for item in self._paginate("documents.list", {"collectionId": collection["id"]}):
                if item.get("archivedAt") or item.get("deletedAt"):
                    continue
                if not item.get("publishedAt"):
                    continue
                author = item.get("createdBy") or {}
                if not author.get("id"):
                    continue
                yield AuthoredDocument(
                    author_id=author["id"],
                    author_name=author.get("name", ""),
                    characters=len((item.get("text") or "").strip()),
                )


def compute_points(documents: Iterable[AuthoredDocument], rules: PointRules) -> list[UserPoints]:
    totals: dict[str, dict] = {}
    for doc in documents:
        entry = totals.setdefault(
            doc.author_id, {"name": doc.author_name, "documents": 0, "characters": 0, "points": 0}
        )
        entry["documents"] += 1
        entry["characters"] += doc.characters
        # 文書ごとに切り捨てる（短い文書を大量に分割しても文字量点が増えないようにする）。
        entry["points"] += rules.points_per_document + doc.characters // rules.characters_per_point

    ordered = sorted(totals.items(), key=lambda kv: (-kv[1]["points"], kv[1]["name"], kv[0]))
    results: list[UserPoints] = []
    for i, (user_id, entry) in enumerate(ordered):
        # 同点は同順位（1, 2, 2, 4 ...）。
        if results and results[-1].points == entry["points"]:
            rank = results[-1].rank
        else:
            rank = i + 1
        results.append(
            UserPoints(
                rank=rank,
                user_id=user_id,
                name=entry["name"],
                documents=entry["documents"],
                characters=entry["characters"],
                points=entry["points"],
            )
        )
    return results


class PointsService:
    """ランキングを一定時間キャッシュする（ページを開くたびにOutline全文書を読まないため）。"""

    def __init__(
        self,
        source: OutlineDocumentSource | None,
        rules: PointRules,
        cache_seconds: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._source = source
        self.rules = rules
        self._cache_seconds = cache_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._cached: tuple[float, list[UserPoints]] | None = None

    @property
    def configured(self) -> bool:
        return self._source is not None

    def ranking(self) -> tuple[float, list[UserPoints]]:
        """(集計時刻のUNIX秒, ランキング) を返す。"""
        if self._source is None:
            raise RuntimeError("Outline APIトークンが未設定です")
        with self._lock:
            now = self._clock()
            if self._cached is None or now - self._cached[0] >= self._cache_seconds:
                self._cached = (now, compute_points(self._source.iter_documents(), self.rules))
            return self._cached
