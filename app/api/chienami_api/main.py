"""chienami-api エントリポイント。

/search はLLMを使用せず、検索結果を返した時点で終了する（design書5.2節）。
mode=semantic（既定, Phase 3）はDense検索のみ、mode=hybrid（Phase 4）は
Dense + KeywordをRRFで統合し、Rerankerで並べ替える。
検索結果は必ず元のOutlineページを開けるURLを含める。

/chat（Phase 4）は出典付きRAG回答を返す（rag.py）。LLM・Rerankerが停止していても
/search（semantic）は動作し続け、/chatのみが503を返す（各Phaseは単独で価値を持つ）。

/points（Issue #77）は文書作成量に応じた貢献ポイントのランキングを返す（points.py）。

/invitations（Issue #81）は招待リンクを発行・一覧・削除する（invitations.py）。管理者限定の
判定はCaddyのforward_auth（Authentik）が行い、通過したリクエストにだけ X-Authentik-Username
が付く。Caddyはクライアントが送った X-Authentik-* を必ず消すため、このヘッダが無い
リクエスト（/search/api/ 等の別経路を含む）は403にする。
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient

from .embedding_client import EmbeddingClient
from .invitations import AuthentikInvitationClient
from .llm_client import LLMClient
from .points import OutlineDocumentSource, PointRules, PointsService
from .rag import AIServiceError, EmbeddingError, RagService, Turn
from .reranker_client import RerankerClient
from .search import SearchService, dedupe_chunks

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("chienami-api")


def _env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"環境変数が未設定です: {name}")
    return value or ""


EMBEDDING_URL = _env("EMBEDDING_URL", "http://embedding:80")
QDRANT_URL = _env("QDRANT_URL", "http://qdrant:6333")
QDRANT_API_KEY = _env("QDRANT_API_KEY", required=True)
QDRANT_COLLECTION = _env("QDRANT_COLLECTION", "chienami_documents")
SEARCH_DEFAULT_LIMIT = int(_env("API_SEARCH_DEFAULT_LIMIT", "10"))
SEARCH_MAX_LIMIT = int(_env("API_SEARCH_MAX_LIMIT", "50"))
RERANKER_URL = _env("RERANKER_URL", "http://reranker:80")
# Hybrid検索でRerankerに渡す候補チャンク数（Dense・Keywordそれぞれの取得件数も同じ）。
HYBRID_CANDIDATES = int(_env("API_HYBRID_CANDIDATES", "20"))
LLM_URL = _env("LLM_URL", "http://llm:80")
LLAMA_API_KEY = _env("LLAMA_API_KEY")
LLM_MAX_TOKENS = int(_env("LLM_MAX_TOKENS", "1024"))
LLM_TIMEOUT_SECONDS = float(_env("LLM_TIMEOUT_SECONDS", "120"))
# RAGでLLMに渡す根拠の最大件数と、根拠として採用するRerank関連度（0〜1）の下限。
RAG_TOP_K = int(_env("RAG_TOP_K", "5"))
RAG_MAX_TOP_K = 10
RAG_MIN_RERANK_SCORE = float(_env("RAG_MIN_RERANK_SCORE", "0.3"))
# 会話の文脈としてLLMに渡す直近の発言数（質問と回答で1往復2件, Issue #87）。0で履歴を使わない。
RAG_HISTORY_MESSAGES = int(_env("RAG_HISTORY_MESSAGES", "6"))
RAG_MAX_HISTORY = 50
# 貢献ポイント（Issue #77）。OUTLINE_API_TOKEN はindexerと共用する（未設定なら/pointsのみ503）。
OUTLINE_INTERNAL_URL = _env("OUTLINE_INTERNAL_URL", "http://outline:3000")
OUTLINE_API_TOKEN = _env("OUTLINE_API_TOKEN")
POINTS_PER_DOCUMENT = int(_env("POINTS_PER_DOCUMENT", "10"))
POINTS_CHARACTERS_PER_POINT = int(_env("POINTS_CHARACTERS_PER_POINT", "100"))
POINTS_CACHE_SECONDS = float(_env("POINTS_CACHE_SECONDS", "300"))
# 招待リンク（Issue #81）。CHIENAMI_INVITE_API_TOKEN が未設定なら/invitationsのみ503。
AUTHENTIK_INTERNAL_URL = _env("AUTHENTIK_INTERNAL_URL", "http://authentik-server:9000")
AUTHENTIK_PUBLIC_URL = _env("AUTHENTIK_PUBLIC_URL", "https://auth.lab.local")
INVITE_FLOW_SLUG = _env("INVITE_FLOW_SLUG", "chienami-invite-enrollment")
CHIENAMI_INVITE_API_TOKEN = _env("CHIENAMI_INVITE_API_TOKEN")
INVITE_MAX_VALID_DAYS = 365

app = FastAPI(title="Chienami API")

qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
search_service = SearchService(qdrant_client, QDRANT_COLLECTION)
embedding_client = EmbeddingClient(EMBEDDING_URL)
reranker_client = RerankerClient(RERANKER_URL)
llm_client = LLMClient(
    LLM_URL, LLAMA_API_KEY, max_tokens=LLM_MAX_TOKENS, timeout=LLM_TIMEOUT_SECONDS
)
rag_service = RagService(
    search_service,
    embedding_client,
    reranker_client,
    llm_client,
    candidates=HYBRID_CANDIDATES,
    top_k=RAG_TOP_K,
    min_score=RAG_MIN_RERANK_SCORE,
    history_messages=RAG_HISTORY_MESSAGES,
)
points_service = PointsService(
    OutlineDocumentSource(OUTLINE_INTERNAL_URL, OUTLINE_API_TOKEN) if OUTLINE_API_TOKEN else None,
    PointRules(
        points_per_document=POINTS_PER_DOCUMENT,
        characters_per_point=POINTS_CHARACTERS_PER_POINT,
    ),
    cache_seconds=POINTS_CACHE_SECONDS,
)
invitation_client = (
    AuthentikInvitationClient(
        AUTHENTIK_INTERNAL_URL, CHIENAMI_INVITE_API_TOKEN, AUTHENTIK_PUBLIC_URL, INVITE_FLOW_SLUG
    )
    if CHIENAMI_INVITE_API_TOKEN
    else None
)


class SearchResultResponse(BaseModel):
    document_id: str
    title: str
    url: str
    score: float
    snippet: str
    chunk_index: int


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultResponse]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=20000)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="質問")
    top_k: int | None = Field(None, ge=1, le=RAG_MAX_TOP_K, description="根拠の最大件数")
    history: list[ChatTurn] = Field(
        default_factory=list, max_length=RAG_MAX_HISTORY, description="これまでの会話（古い順）"
    )


class ChatSourceResponse(BaseModel):
    id: str
    document_id: str
    title: str
    url: str
    snippet: str
    score: float
    chunk_index: int
    cited: bool


class ChatResponse(BaseModel):
    question: str
    answer: str
    abstained: bool
    sources: list[ChatSourceResponse]
    timings: dict[str, int]


class PointRulesResponse(BaseModel):
    points_per_document: int
    characters_per_point: int


class UserPointsResponse(BaseModel):
    rank: int
    user_id: str
    name: str
    documents: int
    characters: int
    points: int


class PointsResponse(BaseModel):
    updated_at: float
    rules: PointRulesResponse
    users: list[UserPointsResponse]


class InvitationRequest(BaseModel):
    valid_days: int = Field(..., ge=1, le=INVITE_MAX_VALID_DAYS, description="有効期間（日）")
    single_use: bool = Field(..., description="1人が登録したら無効にするか")


class InvitationResponse(BaseModel):
    id: str
    url: str
    expires: datetime
    single_use: bool


class InvitationListResponse(BaseModel):
    invitations: list[InvitationResponse]


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, description="検索クエリ"),
    limit: int = Query(SEARCH_DEFAULT_LIMIT, ge=1, le=SEARCH_MAX_LIMIT),
    mode: Literal["semantic", "hybrid"] = Query("semantic", description="検索方式"),
) -> SearchResponse:
    try:
        vectors = embedding_client.embed([q])
    except Exception as exc:
        logger.exception("Embedding取得に失敗しました")
        raise HTTPException(status_code=502, detail="embedding service error") from exc

    if not vectors:
        raise HTTPException(status_code=502, detail="embedding service returned no vector")

    try:
        if mode == "hybrid":
            chunks = search_service.hybrid_chunks(
                q, vectors[0], candidates=max(HYBRID_CANDIDATES, limit), reranker=reranker_client
            )
            results = dedupe_chunks(chunks, limit)
        else:
            results = search_service.search(vectors[0], limit=limit)
    except Exception as exc:
        logger.exception("Qdrant検索に失敗しました")
        raise HTTPException(status_code=502, detail="search backend error") from exc

    return SearchResponse(
        query=q,
        results=[SearchResultResponse(**r.__dict__) for r in results],
    )


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question must not be blank")
    try:
        result = rag_service.answer(
            question,
            top_k=request.top_k,
            history=[Turn(t.role, t.content) for t in request.history],
        )
    except EmbeddingError as exc:
        logger.exception("Embedding取得に失敗しました")
        raise HTTPException(status_code=502, detail="embedding service error") from exc
    except AIServiceError as exc:
        logger.exception("AIサービス（Reranker/LLM）の呼び出しに失敗しました")
        raise HTTPException(status_code=503, detail="AI service unavailable") from exc
    except Exception as exc:
        logger.exception("RAG処理に失敗しました")
        raise HTTPException(status_code=502, detail="search backend error") from exc

    return ChatResponse(
        question=question,
        answer=result.answer,
        abstained=result.abstained,
        sources=[
            ChatSourceResponse(
                id=s.id,
                document_id=s.chunk.document_id,
                title=s.chunk.title,
                url=s.chunk.url,
                snippet=s.chunk.text,
                score=s.chunk.score,
                chunk_index=s.chunk.chunk_index,
                cited=s.cited,
            )
            for s in result.sources
        ],
        timings=result.timings_ms,
    )


@app.get("/points", response_model=PointsResponse)
def points() -> PointsResponse:
    if not points_service.configured:
        raise HTTPException(status_code=503, detail="points service not configured")
    try:
        updated_at, users = points_service.ranking()
    except Exception as exc:
        logger.exception("Outline文書の集計に失敗しました")
        raise HTTPException(status_code=502, detail="outline service error") from exc

    return PointsResponse(
        updated_at=updated_at,
        rules=PointRulesResponse(**points_service.rules.__dict__),
        users=[UserPointsResponse(**u.__dict__) for u in users],
    )


AdminUsername = Annotated[str | None, Header(alias="X-Authentik-Username")]


def _require_invitations(admin: str | None) -> AuthentikInvitationClient:
    if not admin:
        raise HTTPException(status_code=403, detail="admin login required")
    if invitation_client is None:
        raise HTTPException(status_code=503, detail="invitation service not configured")
    return invitation_client


@app.get("/invitations", response_model=InvitationListResponse)
def list_invitations(admin: AdminUsername = None) -> InvitationListResponse:
    client_ = _require_invitations(admin)
    try:
        invitations = client_.list_active()
    except Exception as exc:
        logger.exception("招待の一覧取得に失敗しました")
        raise HTTPException(status_code=502, detail="authentik service error") from exc
    return InvitationListResponse(
        invitations=[InvitationResponse(**i.__dict__) for i in invitations]
    )


@app.post("/invitations", response_model=InvitationResponse, status_code=201)
def create_invitation(
    request: InvitationRequest, admin: AdminUsername = None
) -> InvitationResponse:
    client_ = _require_invitations(admin)
    try:
        invitation = client_.create(request.valid_days, request.single_use)
    except Exception as exc:
        logger.exception("招待の発行に失敗しました")
        raise HTTPException(status_code=502, detail="authentik service error") from exc
    # Authentik上の作成者はサービスアカウントになるため、実際に発行した管理者をログに残す。
    logger.info(
        "招待を発行しました: id=%s by=%s valid_days=%d single_use=%s",
        invitation.id,
        admin,
        request.valid_days,
        request.single_use,
    )
    return InvitationResponse(**invitation.__dict__)


@app.delete("/invitations/{invitation_id}", status_code=204)
def delete_invitation(invitation_id: uuid.UUID, admin: AdminUsername = None) -> Response:
    client_ = _require_invitations(admin)
    try:
        deleted = client_.delete(str(invitation_id))
    except Exception as exc:
        logger.exception("招待の削除に失敗しました")
        raise HTTPException(status_code=502, detail="authentik service error") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="invitation not found")
    logger.info("招待を削除しました: id=%s by=%s", invitation_id, admin)
    return Response(status_code=204)
