"""Translates between MarketMind domain models and ChromaDB's primitive shapes.

Purely structural mapping in both directions — no business logic, no
embedding computation, no filtering or ranking decisions.
"""

from __future__ import annotations

from typing import Any

from app.repositories.knowledge.models import KnowledgeRecord, SearchResult
from app.services.knowledge_ingestion.models import VectorDocument

__all__ = [
    "vector_documents_to_chroma_add_kwargs",
    "chroma_get_result_to_record",
    "chroma_get_result_to_records",
    "chroma_get_result_to_search_results",
    "chroma_query_result_to_search_results",
]


def vector_documents_to_chroma_add_kwargs(documents: list[VectorDocument]) -> dict[str, Any]:
    """Map VectorDocuments into the keyword arguments ChromaDB's `add` expects."""
    return {
        "ids": [document.id for document in documents],
        "documents": [document.text for document in documents],
        "metadatas": [_clean_metadata(document.metadata) for document in documents],
    }


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Drop None values, which ChromaDB metadata does not accept."""
    return {key: value for key, value in metadata.items() if value is not None}


def chroma_get_result_to_record(get_result: dict[str, Any]) -> KnowledgeRecord | None:
    """Map a ChromaDB `get` response for one id into a KnowledgeRecord, or None if empty."""
    ids = get_result.get("ids") or []
    if not ids:
        return None
    documents = get_result.get("documents") or [None]
    metadatas = get_result.get("metadatas") or [{}]
    metadata = metadatas[0] or {}
    return KnowledgeRecord(
        id=ids[0],
        title=metadata.get("title"),
        text=documents[0],
        url=metadata.get("url"),
        published_at=metadata.get("published_at"),
        source_provider_id=metadata.get("source_provider_id"),
        metadata=metadata,
    )


def chroma_get_result_to_records(get_result: dict[str, Any]) -> list[KnowledgeRecord]:
    """Map a ChromaDB `get` response for *multiple* ids (e.g. a `list_all`
    page) into KnowledgeRecords — the many-record counterpart of
    `chroma_get_result_to_record`, which only handles the single-id shape
    (`ids[0]`)."""
    ids = get_result.get("ids") or []
    documents = get_result.get("documents") or []
    metadatas = get_result.get("metadatas") or []

    records: list[KnowledgeRecord] = []
    for index, record_id in enumerate(ids):
        metadata = metadatas[index] if index < len(metadatas) else {}
        metadata = metadata or {}
        text = documents[index] if index < len(documents) else None
        records.append(
            KnowledgeRecord(
                id=record_id,
                title=metadata.get("title"),
                text=text,
                url=metadata.get("url"),
                published_at=metadata.get("published_at"),
                source_provider_id=metadata.get("source_provider_id"),
                metadata=metadata,
            )
        )
    return records


def chroma_get_result_to_search_results(get_result: dict[str, Any]) -> list[SearchResult]:
    """Map a ChromaDB `get` response (a metadata-only/structured lookup,
    no nearest-neighbor ranking) into SearchResults. `score` is always
    None — a `get` response carries no distance, unlike `query`'s own
    `chroma_query_result_to_search_results` counterpart."""
    ids = get_result.get("ids") or []
    documents = get_result.get("documents") or []
    metadatas = get_result.get("metadatas") or []

    results: list[SearchResult] = []
    for index, record_id in enumerate(ids):
        metadata = metadatas[index] if index < len(metadatas) else {}
        text = documents[index] if index < len(documents) else None
        results.append(SearchResult(id=record_id, score=None, text=text, metadata=metadata or {}))
    return results


def chroma_query_result_to_search_results(query_result: dict[str, Any]) -> list[SearchResult]:
    """Map a ChromaDB `query` response (for a single query text) into SearchResults."""
    ids = (query_result.get("ids") or [[]])[0]
    documents = (query_result.get("documents") or [[]])[0]
    metadatas = (query_result.get("metadatas") or [[]])[0]
    distances = (query_result.get("distances") or [[]])[0]

    results: list[SearchResult] = []
    for index, record_id in enumerate(ids):
        metadata = metadatas[index] if index < len(metadatas) else {}
        text = documents[index] if index < len(documents) else None
        distance = distances[index] if index < len(distances) else None
        results.append(
            SearchResult(id=record_id, score=distance, text=text, metadata=metadata or {})
        )
    return results
