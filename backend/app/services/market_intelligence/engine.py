"""Market Intelligence Engine — the first reasoning component of MarketMind AI.

MarketIntelligenceEngine.analyze() turns a list of KnowledgeRecords into a
MarketIntelligence summary using deterministic keyword and frequency rules
only: no LLM call, no sentiment analysis, no stock-movement prediction, and
no recommendation is generated anywhere in this module.
"""

from __future__ import annotations

import re

from app.repositories.knowledge.models import KnowledgeRecord
from app.services.market_intelligence.models import (
    EntityMention,
    MarketIntelligence,
    NewsGroup,
    Theme,
)

__all__ = ["MarketIntelligenceEngine"]

MIN_RECORDS_FOR_THEME = 2
MAX_THEMES = 10
MIN_RECORDS_FOR_FULL_CONFIDENCE = 5

# Seed reference sets for deterministic keyword matching. Not exhaustive —
# intended to be extended as real coverage requirements are defined.
COMPANY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Apple Inc.": ("Apple", "AAPL"),
    "Tesla Inc.": ("Tesla", "TSLA"),
    "Microsoft Corporation": ("Microsoft", "MSFT"),
    "Amazon.com Inc.": ("Amazon", "AMZN"),
    "Alphabet Inc.": ("Alphabet", "Google", "GOOGL"),
    "Meta Platforms Inc.": ("Meta", "Facebook", "META"),
    "NVIDIA Corporation": ("NVIDIA", "NVDA"),
}

SECTOR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Technology": ("tech", "software", "semiconductor", "chip", "chipmaker"),
    "Energy": ("oil", "gas", "energy", "crude", "OPEC"),
    "Financial Services": ("bank", "interest rate", "Federal Reserve", "Fed", "lender"),
    "Healthcare": ("pharma", "drug", "biotech", "vaccine", "FDA"),
    "Automotive": ("automaker", "vehicle", "EV", "electric vehicle"),
}

COUNTRY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "United States": ("United States", "U.S.", "US", "America", "Washington", "Federal Reserve"),
    "China": ("China", "Beijing", "Shanghai", "Chinese"),
    "United Kingdom": ("United Kingdom", "UK", "Britain", "London", "FTSE"),
    "Japan": ("Japan", "Tokyo", "Nikkei", "Japanese"),
    "India": ("India", "Mumbai", "NSE", "BSE", "Indian"),
}

STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "and", "for", "are", "but", "not", "you", "all", "can", "her", "was", "one",
        "our", "out", "day", "get", "has", "him", "his", "how", "man", "new", "now", "old",
        "see", "two", "way", "who", "boy", "did", "its", "let", "put", "say", "she", "too",
        "use", "with", "that", "this", "have", "from", "they", "will", "would", "there",
        "their", "what", "about", "which", "when", "make", "like", "time", "just", "know",
        "take", "into", "year", "your", "good", "some", "could", "them", "than", "then",
        "look", "only", "come", "over", "think", "also", "back", "after", "work", "first",
        "well", "even", "want", "because", "these", "give", "most",
    }
)


class MarketIntelligenceEngine:
    """Deterministically analyzes KnowledgeRecords into MarketIntelligence."""

    def analyze(self, records: list[KnowledgeRecord]) -> MarketIntelligence:
        """Analyze `records` and produce a MarketIntelligence summary.

        Args:
            records: The KnowledgeRecords to analyze.

        Returns:
            A MarketIntelligence summary. Every record is accounted for:
            either through a detected entity/group or via
            `unmatched_record_ids` — no record is silently dropped.
        """
        record_texts = {record.id: self._searchable_text(record) for record in records}

        companies = self._detect_entities(record_texts, COMPANY_KEYWORDS)
        sectors = self._detect_entities(record_texts, SECTOR_KEYWORDS)
        countries = self._detect_entities(record_texts, COUNTRY_KEYWORDS)
        themes = self._detect_themes(record_texts)
        groups = self._group_records(companies, sectors)

        grouped_record_ids = {record_id for group in groups for record_id in group.record_ids}
        unmatched_record_ids = [
            record_id for record_id in record_texts if record_id not in grouped_record_ids
        ]

        return MarketIntelligence(
            total_records_analyzed=len(records),
            groups=groups,
            companies=companies,
            sectors=sectors,
            countries=countries,
            themes=themes,
            unmatched_record_ids=unmatched_record_ids,
        )

    def _searchable_text(self, record: KnowledgeRecord) -> str:
        """Combine a record's title and text into one searchable string."""
        parts = [record.title, record.text]
        return " ".join(part for part in parts if part)

    def _contains_any_keyword(self, text: str, keywords: tuple[str, ...]) -> bool:
        """Match keywords as whole words/phrases, not arbitrary substrings.

        Plain substring matching would let short keywords (e.g. "EV", "US")
        false-match inside unrelated words (e.g. "EV" inside "relevant").
        Word-boundary matching avoids that.
        """
        lowered = text.lower()
        return any(
            re.search(rf"\b{re.escape(keyword.lower())}\b", lowered) is not None
            for keyword in keywords
        )

    def _detect_entities(
        self, record_texts: dict[str, str], reference: dict[str, tuple[str, ...]]
    ) -> list[EntityMention]:
        """Detect entities via case-insensitive keyword substring matching."""
        mentions: list[EntityMention] = []
        for name, keywords in reference.items():
            matching_ids = [
                record_id
                for record_id, text in record_texts.items()
                if text and self._contains_any_keyword(text, keywords)
            ]
            if matching_ids:
                mentions.append(
                    EntityMention(
                        name=name,
                        mention_count=len(matching_ids),
                        supporting_record_ids=matching_ids,
                    )
                )
        return sorted(mentions, key=lambda mention: mention.mention_count, reverse=True)

    def _tokenize(self, text: str) -> set[str]:
        """Extract lowercase alphabetic words of length >= 3, excluding stopwords."""
        words = re.findall(r"[a-zA-Z]{3,}", text.lower())
        return {word for word in words if word not in STOPWORDS}

    def _detect_themes(self, record_texts: dict[str, str]) -> list[Theme]:
        """Detect keywords recurring across at least MIN_RECORDS_FOR_THEME distinct records."""
        keyword_records: dict[str, set[str]] = {}
        for record_id, text in record_texts.items():
            if not text:
                continue
            for word in self._tokenize(text):
                keyword_records.setdefault(word, set()).add(record_id)

        themes = [
            Theme(
                keyword=word,
                occurrence_count=len(record_ids),
                supporting_record_ids=sorted(record_ids),
            )
            for word, record_ids in keyword_records.items()
            if len(record_ids) >= MIN_RECORDS_FOR_THEME
        ]
        themes.sort(key=lambda theme: theme.occurrence_count, reverse=True)
        return themes[:MAX_THEMES]

    def _group_records(
        self, companies: list[EntityMention], sectors: list[EntityMention]
    ) -> list[NewsGroup]:
        """Group records by shared company or sector, computing a confidence score per group.

        Confidence is a simple, transparent function of supporting-evidence
        volume: it scales linearly with the number of supporting records,
        capping at 1.0 once MIN_RECORDS_FOR_FULL_CONFIDENCE is reached.
        """
        groups: list[NewsGroup] = []
        for mention in (*companies, *sectors):
            confidence = round(
                min(1.0, len(mention.supporting_record_ids) / MIN_RECORDS_FOR_FULL_CONFIDENCE), 2
            )
            groups.append(
                NewsGroup(
                    group_key=mention.name,
                    record_ids=mention.supporting_record_ids,
                    confidence_score=confidence,
                )
            )
        return groups
