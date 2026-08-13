"""Evidence Engine — deterministic evidence extraction and organization.

EvidenceEngine.build_graph() creates exactly one EvidenceItem per input
KnowledgeRecord, preserves its provenance fields, and links each item to
whichever companies, sectors, countries, and themes its own text matches.
No reasoning, no LLM, no summarization, no prediction, and no storage
occur anywhere in this module — this engine builds evidence references
only. It reuses the same deterministic keyword reference sets as
MarketIntelligenceEngine (COMPANY_KEYWORDS, SECTOR_KEYWORDS,
COUNTRY_KEYWORDS, STOPWORDS, MIN_RECORDS_FOR_THEME) so both engines agree
on what counts as a company, sector, country, or theme mention.
"""

from __future__ import annotations

import re

from app.repositories.knowledge.models import KnowledgeRecord
from app.services.evidence_engine.models import EvidenceGraph, EvidenceItem
from app.services.market_intelligence.engine import (
    COMPANY_KEYWORDS,
    COUNTRY_KEYWORDS,
    MIN_RECORDS_FOR_THEME,
    SECTOR_KEYWORDS,
    STOPWORDS,
)

__all__ = ["EvidenceEngine"]


class EvidenceEngine:
    """Deterministically builds an EvidenceGraph from KnowledgeRecords."""

    def build_graph(self, records: list[KnowledgeRecord]) -> EvidenceGraph:
        """Build an EvidenceGraph from `records`.

        Args:
            records: The KnowledgeRecords to build evidence from.

        Returns:
            An EvidenceGraph with exactly one EvidenceItem per record, each
            traceable back to its originating record_id. No record is
            skipped, merged, or deduplicated.
        """
        record_texts = {record.id: self._searchable_text(record) for record in records}
        batch_themes = self._detect_batch_themes(record_texts)

        items = [
            self._to_evidence_item(record, record_texts[record.id], batch_themes)
            for record in records
        ]

        return EvidenceGraph(items=items, total_records_processed=len(records))

    def _searchable_text(self, record: KnowledgeRecord) -> str:
        """Combine a record's title and text into one searchable string."""
        parts = [record.title, record.text]
        return " ".join(part for part in parts if part)

    def _contains_any_keyword(self, text: str, keywords: tuple[str, ...]) -> bool:
        """Match keywords as whole words/phrases, not arbitrary substrings."""
        lowered = text.lower()
        return any(
            re.search(rf"\b{re.escape(keyword.lower())}\b", lowered) is not None
            for keyword in keywords
        )

    def _matching_names(self, text: str, reference: dict[str, tuple[str, ...]]) -> list[str]:
        """Return the names in `reference` whose keywords appear in `text`."""
        if not text:
            return []
        return [
            name for name, keywords in reference.items() if self._contains_any_keyword(text, keywords)
        ]

    def _tokenize(self, text: str) -> set[str]:
        """Extract lowercase alphabetic words of length >= 3, excluding stopwords."""
        words = re.findall(r"[a-zA-Z]{3,}", text.lower())
        return {word for word in words if word not in STOPWORDS}

    def _detect_batch_themes(self, record_texts: dict[str, str]) -> set[str]:
        """Detect words recurring across at least MIN_RECORDS_FOR_THEME records in this batch."""
        keyword_records: dict[str, set[str]] = {}
        for record_id, text in record_texts.items():
            if not text:
                continue
            for word in self._tokenize(text):
                keyword_records.setdefault(word, set()).add(record_id)
        return {
            word for word, record_ids in keyword_records.items() if len(record_ids) >= MIN_RECORDS_FOR_THEME
        }

    def _to_evidence_item(
        self, record: KnowledgeRecord, text: str, batch_themes: set[str]
    ) -> EvidenceItem:
        """Build one EvidenceItem, preserving provenance and linking matched entities.

        `source` falls back through `metadata["feed_title"]`, then
        `metadata["source"]`, then `source_provider_id` — KnowledgeRecord
        has no dedicated "source" field distinct from its provider, so this
        is the most specific value available without inventing one.
        """
        source = (
            record.metadata.get("feed_title")
            or record.metadata.get("source")
            or record.source_provider_id
        )
        linked_themes = sorted(word for word in self._tokenize(text) if word in batch_themes) if text else []

        return EvidenceItem(
            record_id=record.id,
            source=source,
            provider=record.source_provider_id,
            url=record.url,
            published_at=record.published_at,
            title=record.title,
            linked_companies=self._matching_names(text, COMPANY_KEYWORDS),
            linked_sectors=self._matching_names(text, SECTOR_KEYWORDS),
            linked_countries=self._matching_names(text, COUNTRY_KEYWORDS),
            linked_themes=linked_themes,
        )
