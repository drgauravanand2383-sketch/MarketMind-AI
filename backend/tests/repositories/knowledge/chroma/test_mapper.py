"""Unit tests for the ChromaDB mapper functions."""

from __future__ import annotations

from app.repositories.knowledge.chroma.mapper import (
    chroma_get_result_to_record,
    chroma_query_result_to_search_results,
    vector_documents_to_chroma_add_kwargs,
)
from app.services.knowledge_ingestion.models import VectorDocument


def test_vector_documents_to_chroma_add_kwargs_maps_fields() -> None:
    documents = [
        VectorDocument(id="doc-1", text="Fed holds rates steady", metadata={"url": "https://x"}),
        VectorDocument(id="doc-2", text="Tech stocks rally", metadata={"url": None}),
    ]

    kwargs = vector_documents_to_chroma_add_kwargs(documents)

    assert kwargs["ids"] == ["doc-1", "doc-2"]
    assert kwargs["documents"] == ["Fed holds rates steady", "Tech stocks rally"]
    assert kwargs["metadatas"] == [{"url": "https://x"}, {}]


def test_vector_documents_to_chroma_add_kwargs_handles_empty_list() -> None:
    kwargs = vector_documents_to_chroma_add_kwargs([])
    assert kwargs == {"ids": [], "documents": [], "metadatas": []}


def test_chroma_get_result_to_record_returns_none_for_empty_result() -> None:
    assert chroma_get_result_to_record({"ids": [], "documents": [], "metadatas": []}) is None


def test_chroma_get_result_to_record_maps_populated_result() -> None:
    result = {
        "ids": ["doc-1"],
        "documents": ["Fed holds rates steady"],
        "metadatas": [{"title": "Fed holds rates steady", "url": "https://example.com/fed"}],
    }

    record = chroma_get_result_to_record(result)

    assert record is not None
    assert record.id == "doc-1"
    assert record.text == "Fed holds rates steady"
    assert record.title == "Fed holds rates steady"
    assert record.url == "https://example.com/fed"


def test_chroma_query_result_to_search_results_maps_all_fields() -> None:
    result = {
        "ids": [["doc-1", "doc-2"]],
        "documents": [["Fed holds rates steady", "Tech stocks rally"]],
        "metadatas": [[{"title": "Fed"}, {"title": "Tech"}]],
        "distances": [[0.1, 0.4]],
    }

    results = chroma_query_result_to_search_results(result)

    assert len(results) == 2
    assert results[0].id == "doc-1"
    assert results[0].score == 0.1
    assert results[1].id == "doc-2"
    assert results[1].score == 0.4


def test_chroma_query_result_to_search_results_handles_empty_result() -> None:
    result = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    assert chroma_query_result_to_search_results(result) == []
