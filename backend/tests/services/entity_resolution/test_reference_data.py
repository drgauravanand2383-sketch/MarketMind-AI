"""Tests for the canonical company reference data.

Verifies `get_company_reference_data()` stays a true superset of
`MarketIntelligenceEngine.COMPANY_KEYWORDS` — this milestone's own §2
"do not invent a second company entity model" constraint, made concrete:
every company MarketIntelligenceEngine/EvidenceEngine already recognize
must also be resolvable here, with the identical name/aliases.
"""

from __future__ import annotations

from app.services.entity_resolution.reference_data import get_company_reference_data
from app.services.market_intelligence.engine import COMPANY_KEYWORDS


def test_every_company_keyword_entry_has_a_reference_record() -> None:
    references = get_company_reference_data()
    canonical_names = {reference.canonical_name for reference in references}

    assert canonical_names == set(COMPANY_KEYWORDS)


def test_reference_aliases_match_company_keywords_exactly() -> None:
    references = {reference.canonical_name: reference for reference in get_company_reference_data()}

    for canonical_name, aliases in COMPANY_KEYWORDS.items():
        assert references[canonical_name].aliases == aliases


def test_every_reference_has_a_unique_entity_id() -> None:
    references = get_company_reference_data()
    entity_ids = [reference.entity_id for reference in references]

    assert len(entity_ids) == len(set(entity_ids))


def test_every_reference_has_a_ticker_and_is_real_looking() -> None:
    """Not a claim of external verification — just a sanity guard that
    every static entry has the fields Company Intelligence (§12) reports."""
    for reference in get_company_reference_data():
        assert reference.ticker
        assert reference.ticker == reference.ticker.upper()
        assert reference.sector
        assert reference.industry
        assert reference.country


def test_get_company_reference_data_is_cached_and_stable() -> None:
    first = get_company_reference_data()
    second = get_company_reference_data()

    assert first is second
