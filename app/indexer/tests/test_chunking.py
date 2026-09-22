import pytest

from chienami_indexer.chunking import chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n   ") == []


def test_short_text_returns_single_chunk():
    chunks = chunk_text("これは短い文書です。", chunk_size=1000, overlap=100)
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].text == "これは短い文書です。"


def test_paragraphs_are_grouped_until_chunk_size():
    paragraphs = ["段落A" * 10, "段落B" * 10, "段落C" * 10]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, chunk_size=len(paragraphs[0]) + len(paragraphs[1]) + 4, overlap=0)
    assert len(chunks) >= 2
    assert "段落A" in chunks[0].text


def test_long_paragraph_is_hard_split():
    long_para = "あ" * 2500
    chunks = chunk_text(long_para, chunk_size=1000, overlap=100)
    assert len(chunks) >= 3
    for c in chunks:
        assert len(c.text) <= 1000


def test_overlap_shares_tail_with_previous_chunk():
    long_para = "".join(f"{i:04d}" for i in range(1000))
    chunks = chunk_text(long_para, chunk_size=200, overlap=50)
    assert len(chunks) >= 2
    prev_tail = chunks[0].text[-50:]
    assert chunks[1].text.startswith(prev_tail)


def test_chunk_indices_are_sequential():
    text = "\n\n".join(["段落" * 200 for _ in range(5)])
    chunks = chunk_text(text, chunk_size=300, overlap=30)
    assert [c.index for c in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize("chunk_size,overlap", [(0, 0), (-1, 0), (100, 100), (100, 200)])
def test_invalid_parameters_raise(chunk_size, overlap):
    with pytest.raises(ValueError):
        chunk_text("text", chunk_size=chunk_size, overlap=overlap)
