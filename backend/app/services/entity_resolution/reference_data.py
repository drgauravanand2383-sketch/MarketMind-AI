"""The canonical company reference set for Entity Resolution (Milestone 12).

Builds `CompanyReference` records — the richer, structured identity shape
`EntityResolutionService` scores against — directly on top of
`app.services.market_intelligence.engine.COMPANY_KEYWORDS`: the same
canonical name + aliases already used by `MarketIntelligenceEngine`,
`EvidenceEngine`, and `CompanyResearchAgent.resolve_company_name()`. This
module adds no new company names beyond that dict; it only attaches
additional real, publicly-known static facts (ticker, exchange, country,
sector, industry, legal name) that `COMPANY_KEYWORDS`'s own
`dict[str, tuple[str, ...]]` shape has no room for.

Per this milestone's own §2 ("do not invent a second company entity
model"), this is deliberately framed as a superset/extension, not a
parallel dataset — if a new company is ever added here without a
corresponding `COMPANY_KEYWORDS` entry, `_build_reference_data()` (below)
raises, and this module's own tests exercise that.

The `COMPANY_KEYWORDS` import is deliberately deferred to inside
`get_company_reference_data()`, not done at module top level:
`market_intelligence.engine` transitively imports
`app.repositories.knowledge` -> `app.services.embedding` ->
`app.services.knowledge_ingestion`, and `knowledge_ingestion.service`
itself imports `entity_resolution.service` (which imports this module) —
an eager top-level import here would close that cycle. Deferring it to
first actual call (i.e. the first real `EntityResolutionService()`
construction, well after every module has finished loading) avoids it
without changing any of those other modules.
"""

from __future__ import annotations

from app.services.entity_resolution.models import CompanyReference

__all__ = ["get_company_reference_data"]

# Additional real, publicly-known static facts per canonical name, layered
# on top of COMPANY_KEYWORDS's (name -> aliases) pairs. `entity_id` is a
# stable, human-readable slug (lowercase ticker) — never a random/opaque
# id, so backfilled Chroma metadata and test fixtures stay legible.
_ADDITIONAL_FACTS: dict[str, dict[str, str]] = {
    "Apple Inc.": {
        "entity_id": "aapl", "legal_name": "Apple Inc.", "ticker": "AAPL",
        "exchange": "NASDAQ", "country": "United States",
        "sector": "Technology", "industry": "Consumer Electronics",
    },
    "Tesla Inc.": {
        "entity_id": "tsla", "legal_name": "Tesla, Inc.", "ticker": "TSLA",
        "exchange": "NASDAQ", "country": "United States",
        "sector": "Automotive", "industry": "Electric Vehicles",
    },
    "Microsoft Corporation": {
        "entity_id": "msft", "legal_name": "Microsoft Corporation", "ticker": "MSFT",
        "exchange": "NASDAQ", "country": "United States",
        "sector": "Technology", "industry": "Software",
    },
    "Amazon.com Inc.": {
        "entity_id": "amzn", "legal_name": "Amazon.com, Inc.", "ticker": "AMZN",
        "exchange": "NASDAQ", "country": "United States",
        "sector": "Consumer Discretionary", "industry": "Internet Retail",
    },
    "Alphabet Inc.": {
        "entity_id": "googl", "legal_name": "Alphabet Inc.", "ticker": "GOOGL",
        "exchange": "NASDAQ", "country": "United States",
        "sector": "Technology", "industry": "Internet Services",
    },
    "Meta Platforms Inc.": {
        "entity_id": "meta", "legal_name": "Meta Platforms, Inc.", "ticker": "META",
        "exchange": "NASDAQ", "country": "United States",
        "sector": "Technology", "industry": "Internet & Social Media",
    },
    "NVIDIA Corporation": {
        "entity_id": "nvda", "legal_name": "NVIDIA Corporation", "ticker": "NVDA",
        "exchange": "NASDAQ", "country": "United States",
        "sector": "Technology", "industry": "Semiconductors",
    },
    "Dell Technologies Inc.": {
        "entity_id": "dell", "legal_name": "Dell Technologies Inc.", "ticker": "DELL",
        "exchange": "NYSE", "country": "United States",
        "sector": "Technology", "industry": "Computer Hardware",
    },
    "Salesforce Inc.": {
        "entity_id": "crm", "legal_name": "Salesforce, Inc.", "ticker": "CRM",
        "exchange": "NYSE", "country": "United States",
        "sector": "Technology", "industry": "Software",
    },
    "Workday Inc.": {
        "entity_id": "wday", "legal_name": "Workday, Inc.", "ticker": "WDAY",
        "exchange": "NASDAQ", "country": "United States",
        "sector": "Technology", "industry": "Software",
    },
    "Reddit Inc.": {
        "entity_id": "rddt", "legal_name": "Reddit, Inc.", "ticker": "RDDT",
        "exchange": "NYSE", "country": "United States",
        "sector": "Technology", "industry": "Internet & Social Media",
    },
    "SanDisk Corporation": {
        "entity_id": "sndk", "legal_name": "SanDisk Corporation", "ticker": "SNDK",
        "exchange": "NASDAQ", "country": "United States",
        "sector": "Technology", "industry": "Semiconductors & Storage",
    },
}


_cache: tuple[CompanyReference, ...] | None = None


def get_company_reference_data() -> tuple[CompanyReference, ...]:
    """Build (and cache) the canonical CompanyReference set, on first call.

    Imports `COMPANY_KEYWORDS` lazily — see this module's own docstring
    for why a top-level import would create a circular import.
    """
    global _cache
    if _cache is None:
        from app.services.market_intelligence.engine import COMPANY_KEYWORDS

        missing = set(COMPANY_KEYWORDS) - set(_ADDITIONAL_FACTS)
        if missing:
            raise RuntimeError(
                f"COMPANY_KEYWORDS has entries with no corresponding entity_resolution "
                f"reference facts: {sorted(missing)!r}. Add them to _ADDITIONAL_FACTS."
            )
        _cache = tuple(
            CompanyReference(
                canonical_name=canonical_name,
                aliases=aliases,
                **_ADDITIONAL_FACTS[canonical_name],
            )
            for canonical_name, aliases in COMPANY_KEYWORDS.items()
        )
    return _cache
