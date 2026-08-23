"""Deterministically assembles a CompanyResearchReport from retrieved data.

No LLM, no AI summarization, no stock-movement prediction, and no
buy/sell recommendation occurs anywhere in this module — every section is
built by direct, rule-based selection and filtering of already-computed
EvidenceGraph, MarketIntelligence, and RelationshipGraph data.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.agents.company_research.models import (
    CompanyOverview,
    CompanyResearchReport,
    CompanyResearchRequest,
    ConfidenceSummary,
    CountryExposure,
    EvidenceReference,
    MarketIntelligenceSummary,
    NewsReference,
    RelationshipReference,
    RiskFlag,
    SectorExposure,
    ThemeExposure,
)
from app.repositories.knowledge.models import KnowledgeRecord
from app.services.entity_resolution.models import CompanyReference
from app.services.evidence_engine.models import EvidenceGraph
from app.services.market_intelligence.engine import COMPANY_KEYWORDS
from app.services.market_intelligence.models import MarketIntelligence
from app.services.market_snapshot.models import MarketSnapshotResult
from app.services.relationship_engine.models import NodeType, RelationshipGraph, RelationshipType

__all__ = ["resolve_company_name", "build_report"]

MIN_RECORDS_FOR_STRONG_CONFIDENCE = 5


def resolve_company_name(
    request: CompanyResearchRequest, market_intelligence: MarketIntelligence
) -> str | None:
    """Resolve which detected company (by canonical name) the request refers to.

    Matches `request.company_name` case-insensitively against detected
    company names (exact or substring in either direction), or
    `request.ticker` against the same keyword reference
    MarketIntelligenceEngine itself uses. Returns None if the request
    doesn't resolve to any formally detected company — this is expected
    (not an error) when the fixed reference set doesn't cover this company.
    """
    target = request.company_name.strip().lower()
    ticker = (request.ticker or "").strip().lower()

    for mention in market_intelligence.companies:
        name_lower = mention.name.lower()
        if target and (target == name_lower or target in name_lower or name_lower in target):
            return mention.name
        if ticker:
            aliases = COMPANY_KEYWORDS.get(mention.name, ())
            if any(alias.lower() == ticker for alias in aliases):
                return mention.name
    return None


def build_report(
    request: CompanyResearchRequest,
    records: list[KnowledgeRecord],
    evidence_graph: EvidenceGraph,
    market_intelligence: MarketIntelligence,
    relationship_graph: RelationshipGraph | None,
    resolved_entity: CompanyReference | None = None,
    market_snapshot: MarketSnapshotResult | None = None,
) -> CompanyResearchReport:
    """Assemble a deterministic CompanyResearchReport.

    `company_overview.matched` reflects whether the Knowledge Repository
    returned any records at all (the "missing company" / "empty
    repository" signal). `entity_recognized` is a separate, narrower
    signal: whether MarketIntelligenceEngine's fixed reference set
    formally detected this company among the retrieved records. A company
    can be matched (records found) without being entity_recognized (not
    yet in the reference set) — that limitation is surfaced as a Key Risk,
    not hidden.

    Args:
        request: The original research request.
        records: The KnowledgeRecords retrieved from the Knowledge Repository.
        evidence_graph: Evidence built from `records`.
        market_intelligence: Market intelligence analyzed from `records`.
        relationship_graph: Relationships derived from `market_intelligence`,
            or None if `request.include_relationships` was False.
        resolved_entity: The canonical entity `request.company_name`/
            `.ticker` resolved to (Milestone 12's
            `EntityResolutionService.lookup_by_name_or_ticker`), or None
            when no entity-resolution service was injected into the
            calling agent, or the company isn't in the reference set.
            Purely additive — populates `company_overview`'s new
            `resolved_*`/`sector`/`industry`/`country` fields only; every
            other section is computed exactly as before this parameter
            existed.
        market_snapshot: The market snapshot for `resolved_entity`
            (Milestone 13's `MarketSnapshotService.get_snapshot`), or
            None when no `market_snapshot_service` was injected into the
            calling agent. Passed straight through onto the returned
            report's own `market_snapshot` field — this function performs
            no market-data logic of its own.

    Returns:
        A CompanyResearchReport covering all nine required sections.
    """
    resolved_name = resolve_company_name(request, market_intelligence)
    mention = next((m for m in market_intelligence.companies if m.name == resolved_name), None)
    group = next((g for g in market_intelligence.groups if g.group_key == resolved_name), None)

    supporting_ids = (
        set(mention.supporting_record_ids) if mention else {record.id for record in records}
    )

    company_overview = CompanyOverview(
        company_name=resolved_name or (resolved_entity.canonical_name if resolved_entity else request.company_name),
        ticker=request.ticker or (resolved_entity.ticker if resolved_entity else None),
        matched=len(records) > 0,
        entity_recognized=mention is not None,
        mention_count=mention.mention_count if mention else 0,
        supporting_record_ids=sorted(supporting_ids),
        resolved_entity_id=resolved_entity.entity_id if resolved_entity else None,
        resolution_confidence=1.0 if resolved_entity else None,
        resolution_method="direct_lookup" if resolved_entity else None,
        sector=resolved_entity.sector if resolved_entity else None,
        industry=resolved_entity.industry if resolved_entity else None,
        country=resolved_entity.country if resolved_entity else None,
    )

    latest_news = [
        NewsReference(
            record_id=record.id,
            title=record.title,
            url=record.url,
            published_at=record.published_at,
            source=record.source_provider_id,
        )
        for record in records
    ]

    market_intelligence_summary = MarketIntelligenceSummary(
        mention_count=mention.mention_count if mention else 0,
        group_confidence=group.confidence_score if group else None,
        supporting_record_ids=sorted(supporting_ids),
    )

    relationship_analysis, sector_analysis, country_exposure = _build_relationship_sections(
        relationship_graph, resolved_name
    )
    theme_analysis = _build_theme_analysis(market_intelligence, supporting_ids)

    supporting_evidence = _build_supporting_evidence(
        request, evidence_graph, records, resolved_name
    )

    confidence_summary = ConfidenceSummary(
        overall_confidence=group.confidence_score if group else 0.0,
        supporting_record_count=len(supporting_ids),
        basis=(
            f"Based on {len(supporting_ids)} supporting record(s); confidence scales "
            f"linearly up to {MIN_RECORDS_FOR_STRONG_CONFIDENCE} corroborating records."
        ),
    )

    key_risks = _build_key_risks(
        matched=company_overview.matched,
        entity_recognized=company_overview.entity_recognized,
        supporting_record_count=len(supporting_ids),
        sector_analysis=sector_analysis,
        country_exposure=country_exposure,
    )

    return CompanyResearchReport(
        request=request,
        generated_at=datetime.now(UTC),
        company_overview=company_overview,
        latest_news=latest_news,
        market_intelligence=market_intelligence_summary,
        relationship_analysis=relationship_analysis,
        sector_analysis=sector_analysis,
        country_exposure=country_exposure,
        theme_analysis=theme_analysis,
        supporting_evidence=supporting_evidence,
        confidence_summary=confidence_summary,
        key_risks=key_risks,
        market_snapshot=market_snapshot,
    )


def _build_relationship_sections(
    relationship_graph: RelationshipGraph | None, resolved_name: str | None
) -> tuple[list[RelationshipReference], list[SectorExposure], list[CountryExposure]]:
    """Build Sections 4-6 from edges touching this company's node, if available."""
    relationship_analysis: list[RelationshipReference] = []
    sector_analysis: list[SectorExposure] = []
    country_exposure: list[CountryExposure] = []

    if relationship_graph is None or resolved_name is None:
        return relationship_analysis, sector_analysis, country_exposure

    company_node_id = f"{NodeType.COMPANY.value}:{resolved_name}"
    nodes_by_id = {node.id: node for node in relationship_graph.nodes}

    for edge in relationship_graph.edges:
        if edge.source_id != company_node_id and edge.target_id != company_node_id:
            continue
        other_id = edge.target_id if edge.source_id == company_node_id else edge.source_id
        other_node = nodes_by_id.get(other_id)
        other_label = other_node.label if other_node else other_id

        relationship_analysis.append(
            RelationshipReference(
                related_id=other_id,
                related_label=other_label,
                relationship_type=edge.relationship_type.value,
                weight=edge.weight,
            )
        )
        if edge.relationship_type == RelationshipType.COMPANY_TO_SECTOR:
            sector_analysis.append(SectorExposure(sector=other_label, weight=edge.weight))
        elif edge.relationship_type == RelationshipType.COMPANY_TO_COUNTRY:
            country_exposure.append(CountryExposure(country=other_label, weight=edge.weight))

    return relationship_analysis, sector_analysis, country_exposure


def _build_theme_analysis(
    market_intelligence: MarketIntelligence, supporting_ids: set[str]
) -> list[ThemeExposure]:
    """Themes whose evidence overlaps this company's own supporting records."""
    results = [
        ThemeExposure(
            keyword=theme.keyword,
            occurrence_count=len(supporting_ids & set(theme.supporting_record_ids)),
        )
        for theme in market_intelligence.themes
        if supporting_ids & set(theme.supporting_record_ids)
    ]
    return sorted(results, key=lambda item: item.keyword)


def _build_supporting_evidence(
    request: CompanyResearchRequest,
    evidence_graph: EvidenceGraph,
    records: list[KnowledgeRecord],
    resolved_name: str | None,
) -> list[EvidenceReference]:
    """Build Section 7.

    Filters to items formally linked to the resolved company when
    possible (most precise); falls back to evidence for every retrieved
    record when the company wasn't formally recognized, so search results
    are never silently hidden by a reference-set gap.
    """
    if not request.include_evidence:
        return []

    if resolved_name is not None:
        matching_items = [
            item for item in evidence_graph.items if resolved_name in item.linked_companies
        ]
    else:
        retrieved_ids = {record.id for record in records}
        matching_items = [item for item in evidence_graph.items if item.record_id in retrieved_ids]

    return [
        EvidenceReference(
            record_id=item.record_id,
            source=item.source,
            provider=item.provider,
            url=item.url,
            published_at=item.published_at,
            title=item.title,
        )
        for item in matching_items
    ]


def _build_key_risks(
    *,
    matched: bool,
    entity_recognized: bool,
    supporting_record_count: int,
    sector_analysis: list[SectorExposure],
    country_exposure: list[CountryExposure],
) -> list[RiskFlag]:
    """Deterministic data-quality/coverage flags only — never a market or price prediction."""
    if not matched:
        return [
            RiskFlag(code="NO_DATA", description="No knowledge records matched this company.")
        ]

    risks: list[RiskFlag] = []
    if not entity_recognized:
        risks.append(
            RiskFlag(
                code="ENTITY_NOT_RECOGNIZED",
                description=(
                    "Records were found, but this company is not in the deterministic "
                    "entity reference set; structured analysis may be incomplete."
                ),
            )
        )
    if supporting_record_count < MIN_RECORDS_FOR_STRONG_CONFIDENCE:
        risks.append(
            RiskFlag(
                code="LOW_EVIDENCE_COVERAGE",
                description=(
                    f"Only {supporting_record_count} supporting record(s) found; "
                    "confidence in this report is limited by evidence volume."
                ),
            )
        )
    if not sector_analysis:
        risks.append(
            RiskFlag(
                code="NO_SECTOR_CONTEXT",
                description="No sector association could be determined from available records.",
            )
        )
    if not country_exposure:
        risks.append(
            RiskFlag(
                code="NO_COUNTRY_CONTEXT",
                description="No geographic exposure could be determined from available records.",
            )
        )
    return risks
