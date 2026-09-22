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
