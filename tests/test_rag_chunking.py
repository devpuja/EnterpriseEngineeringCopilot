import pytest

from app.rag.chunking import chunk_text


def test_chunk_text_returns_single_chunk_for_short_text():
    assert chunk_text("Azure AI Search retrieves documents.", chunk_size=100, overlap=10) == [
        "Azure AI Search retrieves documents."
    ]


def test_chunk_text_chunks_long_text_with_overlap():
    text = "A" * 30 + " " + "B" * 30 + " " + "C" * 30
    chunks = chunk_text(text, chunk_size=40, overlap=10)
    assert len(chunks) >= 3
    assert all(chunks)
    assert any("B" in chunk for chunk in chunks)


def test_chunk_text_rejects_invalid_overlap():
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size=10, overlap=10)


def test_chunk_text_empty_input_returns_empty_list():
    assert chunk_text(" \n ") == []
