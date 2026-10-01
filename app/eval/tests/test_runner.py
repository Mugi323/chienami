import httpx
import respx

from chienami_eval.metrics import EvalCase
from chienami_eval.runner import load_cases, run


def test_load_cases_parses_yaml(tmp_path):
    yaml_content = """
cases:
  - query: "テスト質問1"
    expected_urls:
      - "https://x/doc/a"
  - query: "テスト質問2"
    expected_urls: []
"""
    path = tmp_path / "questions.yaml"
    path.write_text(yaml_content, encoding="utf-8")

    cases = load_cases(str(path))
    assert len(cases) == 2
    assert cases[0].query == "テスト質問1"
    assert cases[0].expected_urls == ("https://x/doc/a",)
    assert cases[1].expected_urls == ()


def test_load_cases_empty_file(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    assert load_cases(str(path)) == []


@respx.mock
def test_run_queries_api_and_builds_results():
    respx.get("http://api.test/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "query": "質問",
                "results": [
                    {
                        "document_id": "d1",
                        "title": "t",
                        "url": "https://x/doc/a",
                        "score": 0.9,
                        "snippet": "s",
                        "chunk_index": 0,
                    }
                ],
            },
        )
    )

    cases = [EvalCase(query="質問", expected_urls=("https://x/doc/a",))]
    results = run(cases, base_url="http://api.test", max_k=10)

    assert len(results) == 1
    assert results[0].hit_ranks == (1,)


# --- 検索方式の比較・RAG評価（Phase 4） ---

import json  # noqa: E402

from chienami_eval.runner import main, run_rag  # noqa: E402


def _search_body(urls):
    return {
        "query": "q",
        "results": [
            {
                "document_id": "d",
                "title": "t",
                "url": u,
                "score": 0.5,
                "snippet": "",
                "chunk_index": 0,
            }
            for u in urls
        ],
    }


@respx.mock
def test_run_passes_mode_and_skips_unanswerable_cases():
    route = respx.get("http://api.test/search").mock(
        return_value=httpx.Response(200, json=_search_body(["https://x/doc/a"]))
    )
    cases = [
        EvalCase(query="答えあり", expected_urls=("https://x/doc/a",)),
        EvalCase(query="答えなし", expected_urls=()),
    ]
    results = run(cases, base_url="http://api.test", max_k=5, mode="hybrid")

    assert len(results) == 1
    assert route.call_count == 1
    params = route.calls[0].request.url.params
    assert params["mode"] == "hybrid"
    assert params["q"] == "答えあり"


@respx.mock
def test_run_rag_posts_question_and_builds_results():
    route = respx.post("http://api.test/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "question": "q",
                "answer": "a[S1]",
                "abstained": False,
                "sources": [{"id": "S1", "url": "https://x/doc/a", "cited": True}],
                "timings": {"search_ms": 1, "rerank_ms": 2, "llm_ms": 3},
            },
        )
    )
    cases = [EvalCase(query="質問", expected_urls=("https://x/doc/a",))]
    [result] = run_rag(cases, base_url="http://api.test")

    assert json.loads(route.calls[0].request.content) == {"question": "質問"}
    assert result.cited_urls == ("https://x/doc/a",)
    assert result.total_ms == 6


@respx.mock
def test_main_compares_modes_and_reports_rag(tmp_path, capsys):
    path = tmp_path / "questions.yaml"
    path.write_text(
        'cases:\n  - query: "PCR"\n    expected_urls: ["https://x/doc/a"]\n'
        '  - query: "天気"\n    expected_urls: []\n',
        encoding="utf-8",
    )

    def _search(request):
        mode = request.url.params["mode"]
        urls = ["https://x/doc/z", "https://x/doc/a"] if mode == "semantic" else ["https://x/doc/a"]
        return httpx.Response(200, json=_search_body(urls))

    def _chat(request):
        question = json.loads(request.content)["question"]
        if question == "天気":
            return httpx.Response(200, json={"abstained": True, "sources": [], "timings": {}})
        return httpx.Response(
            200,
            json={
                "abstained": False,
                "sources": [{"id": "S1", "url": "https://x/doc/a", "cited": True}],
                "timings": {"llm_ms": 2000},
            },
        )

    respx.get("http://api.test/search").mock(side_effect=_search)
    respx.post("http://api.test/chat").mock(side_effect=_chat)

    code = main(
        [
            str(path),
            "--base-url",
            "http://api.test",
            "--k",
            "1,5",
            "--mode",
            "semantic,hybrid",
            "--rag",
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "[検索方式の比較]" in out
    # semantic は2位、hybrid は1位で正解を取得する。
    assert "Recall@1         0.000     1.000" in out
    assert "MRR              0.500     1.000" in out
    assert "[引用OK] 2.0s  PCR" in out
    assert "[控えた] 0.0s  天気" in out
    assert "回答を控えた割合:       1.000" in out


def test_main_rejects_unknown_mode(tmp_path):
    import pytest

    path = tmp_path / "questions.yaml"
    path.write_text('cases:\n  - query: "q"\n    expected_urls: ["u"]\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        main([str(path), "--mode", "magic"])
