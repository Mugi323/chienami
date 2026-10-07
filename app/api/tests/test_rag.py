import pytest

from chienami_api.rag import (
    ABSTAIN_ANSWER,
    HISTORY_MAX_CHARS,
    NO_ANSWER_TEXT,
    REWRITE_SYSTEM_PROMPT,
    SEARCH_QUERY_MAX_CHARS,
    SOURCE_MAX_CHARS,
    SYSTEM_PROMPT,
    AIServiceError,
    EmbeddingError,
    RagService,
    Turn,
    build_messages,
    build_rewrite_messages,
    extract_citations,
    is_no_answer,
    parse_search_query,
    select_sources,
    trim_history,
)
from chienami_api.search import Chunk


def _chunk(document_id: str, score: float, text: str = "", chunk_index: int = 0) -> Chunk:
    return Chunk(
        document_id=document_id,
        title=f"タイトル{document_id}",
        url=f"https://knowledge.lab.local/doc/{document_id}",
        chunk_index=chunk_index,
        text=text or f"本文{document_id}",
        score=score,
    )


# --- 純関数 ---


def test_select_sources_applies_threshold_and_top_k():
    chunks = [_chunk("a", 0.9), _chunk("b", 0.8), _chunk("c", 0.5), _chunk("d", 0.1)]
    assert [c.document_id for c in select_sources(chunks, top_k=2, min_score=0.3)] == ["a", "b"]
    assert [c.document_id for c in select_sources(chunks, top_k=5, min_score=0.3)] == [
        "a",
        "b",
        "c",
    ]
    assert select_sources(chunks, top_k=5, min_score=0.95) == []


def test_build_messages_labels_sources_in_order():
    messages = build_messages("PCRの温度は？", [_chunk("a", 0.9, "58度"), _chunk("b", 0.8, "60度")])
    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    user = messages[1]["content"]
    assert messages[1]["role"] == "user"
    assert "[S1] タイトル: タイトルa\n58度" in user
    assert "[S2] タイトル: タイトルb\n60度" in user
    assert user.index("[S1]") < user.index("[S2]") < user.index("PCRの温度は？")


def test_build_messages_truncates_long_source():
    messages = build_messages("q", [_chunk("a", 0.9, "あ" * (SOURCE_MAX_CHARS + 100))])
    assert "あ" * SOURCE_MAX_CHARS in messages[1]["content"]
    assert "あ" * (SOURCE_MAX_CHARS + 1) not in messages[1]["content"]


def test_build_messages_puts_history_between_system_and_question():
    history = [Turn("user", "PCRの温度は？"), Turn("assistant", "58度です。")]
    messages = build_messages("時間は？", [_chunk("a", 0.9, "30秒")], history)
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[1]["content"] == "PCRの温度は？"
    assert messages[2]["content"] == "58度です。"
    assert "30秒" in messages[3]["content"] and "時間は？" in messages[3]["content"]


def test_trim_history_keeps_recent_strips_citations_and_truncates():
    history = [
        Turn("user", "古い質問"),
        Turn("assistant", "古い回答[S1]"),
        Turn("user", "  PCRの温度は？ "),
        Turn("assistant", "58度です[S1][S2]。"),
        Turn("user", "あ" * (HISTORY_MAX_CHARS + 10)),
        Turn("assistant", "[S1]"),
    ]
    trimmed = trim_history(history, max_messages=4)
    assert trimmed == [
        Turn("user", "PCRの温度は？"),
        Turn("assistant", "58度です。"),
        Turn("user", "あ" * HISTORY_MAX_CHARS),
    ]
    assert trim_history(history, max_messages=0) == []


def test_build_rewrite_messages_includes_conversation_and_question():
    messages = build_rewrite_messages(
        "その手順は？", [Turn("user", "PCRとは？"), Turn("assistant", "DNAを増やす方法です。")]
    )
    assert messages[0] == {"role": "system", "content": REWRITE_SYSTEM_PROMPT}
    user = messages[1]["content"]
    assert "ユーザー: PCRとは？" in user
    assert "アシスタント: DNAを増やす方法です。" in user
    assert user.index("DNAを増やす") < user.index("その手順は？")


def test_parse_search_query():
    assert parse_search_query("PCRの手順", "q") == "PCRの手順"
    assert parse_search_query("\n検索クエリ：「PCRの手順」\n説明", "q") == "PCRの手順"
    assert parse_search_query("  \n ", "元の質問") == "元の質問"
    assert len(parse_search_query("あ" * 500, "q")) == SEARCH_QUERY_MAX_CHARS


def test_system_prompt_states_design_principles():
    assert "断定しない" in SYSTEM_PROMPT
    assert NO_ANSWER_TEXT in SYSTEM_PROMPT
    assert "[S1]" in SYSTEM_PROMPT
    assert "```" in SYSTEM_PROMPT


def test_extract_citations_ordered_unique_and_in_range():
    answer = "58度です[S2]。プライマーも確認します[S1][S2]。[S9]は存在しない。[S0]"
    assert extract_citations(answer, source_count=3) == [2, 1]


def test_extract_citations_none():
    assert extract_citations("出典なしの回答", source_count=3) == []


def test_is_no_answer():
    assert is_no_answer("資料からは分かりません。")
    assert is_no_answer("  資料からは分かりません")
    assert not is_no_answer("58度です[S1]。")


# --- RagService ---


class _Embedder:
    def __init__(self, vectors=None, error=None):
        self.vectors = [[0.1]] if vectors is None else vectors
        self.error = error

    def embed(self, texts):
        if self.error:
            raise self.error
        return self.vectors


class _Search:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []

    def candidate_chunks(self, query, vector, candidates):
        self.calls.append((query, vector, candidates))
        return self.chunks


class _Reranker:
    def __init__(self, ranked=None, error=None):
        self.ranked = ranked or []
        self.error = error

    def rerank(self, query, texts):
        if self.error:
            raise self.error
        return self.ranked


class _LLM:
    def __init__(self, answer="", error=None, rewrite="書き換えたクエリ", rewrite_error=None):
        self.answer = answer
        self.error = error
        self.rewrite = rewrite
        self.rewrite_error = rewrite_error
        self.messages = None
        self.rewrite_messages = None

    def chat(self, messages):
        if messages[0]["content"] == REWRITE_SYSTEM_PROMPT:
            self.rewrite_messages = messages
            if self.rewrite_error:
                raise self.rewrite_error
            return self.rewrite
        self.messages = messages
        if self.error:
            raise self.error
        return self.answer


def _service(chunks, ranked, llm, embedder=None, reranker=None, **kwargs):
    return RagService(
        _Search(chunks),
        embedder or _Embedder(),
        reranker or _Reranker(ranked),
        llm,
        **kwargs,
    )


def test_answer_with_citations():
    chunks = [_chunk("a", 0.03, "無関係"), _chunk("b", 0.02, "アニーリング温度は58度")]
    llm = _LLM("アニーリング温度は58度です[S1]。")
    result = _service(chunks, [(1, 0.95), (0, 0.01)], llm, min_score=0.3).answer("温度は？")

    assert result.answer == "アニーリング温度は58度です[S1]。"
    assert not result.abstained
    assert [(s.id, s.chunk.document_id, s.chunk.score, s.cited) for s in result.sources] == [
        ("S1", "b", 0.95, True)
    ]
    assert "アニーリング温度は58度" in llm.messages[1]["content"]
    assert set(result.timings_ms) == {"search_ms", "rerank_ms", "llm_ms"}


def test_answer_marks_uncited_sources():
    chunks = [_chunk("a", 0), _chunk("b", 0)]
    llm = _LLM("答え[S2]。")
    result = _service(chunks, [(0, 0.9), (1, 0.8)], llm).answer("q")
    assert [(s.id, s.cited) for s in result.sources] == [("S1", False), ("S2", True)]


def test_answer_abstains_without_calling_llm_when_no_source_passes_threshold():
    llm = _LLM("呼ばれないはず")
    result = _service([_chunk("a", 0)], [(0, 0.05)], llm, min_score=0.3).answer("q")
    assert result.abstained
    assert result.answer == ABSTAIN_ANSWER
    assert result.sources == []
    assert llm.messages is None
    assert result.timings_ms["llm_ms"] == 0


def test_answer_abstains_when_no_candidates():
    llm = _LLM("呼ばれないはず")
    result = _service([], [], llm).answer("q")
    assert result.abstained
    assert llm.messages is None


def test_answer_flags_llm_no_answer_as_abstained():
    llm = _LLM(NO_ANSWER_TEXT)
    result = _service([_chunk("a", 0)], [(0, 0.9)], llm).answer("q")
    assert result.abstained
    assert result.answer == NO_ANSWER_TEXT
    assert [s.cited for s in result.sources] == [False]


def test_answer_respects_top_k_override():
    chunks = [_chunk(str(i), 0) for i in range(5)]
    ranked = [(i, 0.9 - i * 0.01) for i in range(5)]
    llm = _LLM("答え[S1]")
    result = _service(chunks, ranked, llm, top_k=5).answer("q", top_k=2)
    assert len(result.sources) == 2


def test_answer_passes_candidates_setting_to_search():
    search = _Search([])
    RagService(search, _Embedder(), _Reranker(), _LLM(), candidates=7).answer("質問")
    assert search.calls == [("質問", [0.1], 7)]


def test_answer_raises_embedding_error():
    with pytest.raises(EmbeddingError):
        _service([], [], _LLM(), embedder=_Embedder(error=RuntimeError("down"))).answer("q")
    with pytest.raises(EmbeddingError):
        _service([], [], _LLM(), embedder=_Embedder(vectors=[])).answer("q")


def test_answer_raises_ai_service_error_on_reranker_failure():
    reranker = _Reranker(error=RuntimeError("down"))
    with pytest.raises(AIServiceError):
        _service([_chunk("a", 0)], [], _LLM(), reranker=reranker).answer("q")


def test_answer_raises_ai_service_error_on_llm_failure():
    llm = _LLM(error=RuntimeError("down"))
    with pytest.raises(AIServiceError):
        _service([_chunk("a", 0)], [(0, 0.9)], llm).answer("q")


# --- 会話履歴（Issue #87） ---


class _RecordingEmbedder(_Embedder):
    def __init__(self):
        super().__init__()
        self.texts = None

    def embed(self, texts):
        self.texts = texts
        return super().embed(texts)


def test_answer_with_history_searches_with_rewritten_query():
    search = _Search([_chunk("a", 0, "手順本文")])
    embedder = _RecordingEmbedder()
    llm = _LLM("手順です[S1]。", rewrite="PCRの手順")
    history = [Turn("user", "PCRとは？"), Turn("assistant", "DNAを増やす方法です[S1]。")]
    result = RagService(search, embedder, _Reranker([(0, 0.9)]), llm).answer(
        "その手順は？", history=history
    )

    assert embedder.texts == ["PCRの手順"]
    assert search.calls[0][0] == "PCRの手順"
    assert "その手順は？" in llm.rewrite_messages[1]["content"]
    # 回答には書き換え前の質問と、[Sn]を除いた履歴を渡す
    assert llm.messages[1] == {"role": "user", "content": "PCRとは？"}
    assert llm.messages[2] == {"role": "assistant", "content": "DNAを増やす方法です。"}
    assert llm.messages[3]["content"].endswith("その手順は？")
    assert result.answer == "手順です[S1]。"
    assert "rewrite_ms" in result.timings_ms


def test_answer_without_history_does_not_rewrite():
    embedder = _RecordingEmbedder()
    llm = _LLM("答え[S1]")
    RagService(_Search([_chunk("a", 0)]), embedder, _Reranker([(0, 0.9)]), llm).answer("質問")
    assert llm.rewrite_messages is None
    assert embedder.texts == ["質問"]


def test_answer_ignores_history_when_disabled():
    llm = _LLM("答え[S1]")
    _service([_chunk("a", 0)], [(0, 0.9)], llm, history_messages=0).answer(
        "質問", history=[Turn("user", "前の質問")]
    )
    assert llm.rewrite_messages is None
    assert len(llm.messages) == 2


def test_answer_raises_ai_service_error_on_rewrite_failure():
    llm = _LLM(rewrite_error=RuntimeError("down"))
    with pytest.raises(AIServiceError):
        _service([_chunk("a", 0)], [(0, 0.9)], llm).answer("q", history=[Turn("user", "前")])
