"""Unit tests for RelationshipEngine.

All relationships exercised here are established purely by shared
supporting_record_ids — no LLM, inference, or prediction is involved.
"""

from __future__ import annotations

from app.services.market_intelligence.engine import MarketIntelligenceEngine
from app.services.market_intelligence.models import EntityMention, MarketIntelligence, Theme
from app.services.relationship_engine.engine import RelationshipEngine
from app.services.relationship_engine.models import NodeType, RelationshipType
from tests.services.market_intelligence.test_engine import _record


def _mention(name: str, record_ids: list[str]) -> EntityMention:
    return EntityMention(name=name, mention_count=len(record_ids), supporting_record_ids=record_ids)


def _theme(keyword: str, record_ids: list[str]) -> Theme:
    return Theme(keyword=keyword, occurrence_count=len(record_ids), supporting_record_ids=record_ids)


def _intelligence(
    companies: list[EntityMention] | None = None,
    sectors: list[EntityMention] | None = None,
    countries: list[EntityMention] | None = None,
    themes: list[Theme] | None = None,
) -> MarketIntelligence:
    return MarketIntelligence(
        total_records_analyzed=0,
        groups=[],
        companies=companies or [],
        sectors=sectors or [],
        countries=countries or [],
        themes=themes or [],
        unmatched_record_ids=[],
    )


def test_empty_intelligence_produces_empty_graph() -> None:
    engine = RelationshipEngine()
    graph = engine.build_graph(_intelligence())

    assert graph.nodes == []
    assert graph.edges == []


def test_company_to_sector_edge_created_when_evidence_overlaps() -> None:
    engine = RelationshipEngine()
    intelligence = _intelligence(
        companies=[_mention("Apple Inc.", ["rec-1"])],
        sectors=[_mention("Technology", ["rec-1"])],
    )

    graph = engine.build_graph(intelligence)

    edges = [e for e in graph.edges if e.relationship_type == RelationshipType.COMPANY_TO_SECTOR]
    assert len(edges) == 1
    assert edges[0].source_id == "company:Apple Inc."
    assert edges[0].target_id == "sector:Technology"
    assert edges[0].weight == 1
    assert edges[0].supporting_record_ids == ["rec-1"]


def test_company_to_country_edge_created_when_evidence_overlaps() -> None:
    engine = RelationshipEngine()
    intelligence = _intelligence(
        companies=[_mention("Apple Inc.", ["rec-1"])],
        countries=[_mention("United States", ["rec-1"])],
    )

    graph = engine.build_graph(intelligence)

    edges = [e for e in graph.edges if e.relationship_type == RelationshipType.COMPANY_TO_COUNTRY]
    assert len(edges) == 1
    assert edges[0].source_id == "company:Apple Inc."
    assert edges[0].target_id == "country:United States"


def test_sector_to_theme_edge_created_when_evidence_overlaps() -> None:
    engine = RelationshipEngine()
    intelligence = _intelligence(
        sectors=[_mention("Financial Services", ["rec-4", "rec-5"])],
        themes=[_theme("rates", ["rec-4", "rec-5"])],
    )

    graph = engine.build_graph(intelligence)

    edges = [e for e in graph.edges if e.relationship_type == RelationshipType.SECTOR_TO_THEME]
    assert len(edges) == 1
    assert edges[0].source_id == "sector:Financial Services"
    assert edges[0].target_id == "theme:rates"
    assert edges[0].weight == 2


def test_theme_to_theme_edge_created_for_co_occurring_themes() -> None:
    engine = RelationshipEngine()
    intelligence = _intelligence(
        themes=[_theme("earnings", ["rec-1", "rec-3"]), _theme("quarterly", ["rec-1", "rec-3"])]
    )

    graph = engine.build_graph(intelligence)

    edges = [e for e in graph.edges if e.relationship_type == RelationshipType.THEME_TO_THEME]
    assert len(edges) == 1
    assert {edges[0].source_id, edges[0].target_id} == {"theme:earnings", "theme:quarterly"}
    assert edges[0].weight == 2


def test_company_to_company_edge_created_for_co_mentioned_companies() -> None:
    engine = RelationshipEngine()
    intelligence = _intelligence(
        companies=[
            _mention("Apple Inc.", ["rec-3"]),
            _mention("Tesla Inc.", ["rec-3"]),
        ]
    )

    graph = engine.build_graph(intelligence)

    edges = [e for e in graph.edges if e.relationship_type == RelationshipType.COMPANY_TO_COMPANY]
    assert len(edges) == 1
    assert {edges[0].source_id, edges[0].target_id} == {"company:Apple Inc.", "company:Tesla Inc."}


def test_no_edge_created_when_evidence_does_not_overlap() -> None:
    engine = RelationshipEngine()
    intelligence = _intelligence(
        companies=[_mention("Apple Inc.", ["rec-1"])],
        sectors=[_mention("Energy", ["rec-9"])],
    )

    graph = engine.build_graph(intelligence)

    assert graph.edges == []


def test_weight_equals_number_of_shared_records() -> None:
    engine = RelationshipEngine()
    intelligence = _intelligence(
        companies=[_mention("Apple Inc.", ["rec-1", "rec-2", "rec-3"])],
        sectors=[_mention("Technology", ["rec-1", "rec-2", "rec-9"])],
    )

    graph = engine.build_graph(intelligence)

    edge = graph.edges[0]
    assert edge.weight == 2
    assert set(edge.supporting_record_ids) == {"rec-1", "rec-2"}


def test_isolated_entities_still_appear_as_nodes_without_edges() -> None:
    engine = RelationshipEngine()
    intelligence = _intelligence(
        companies=[_mention("Apple Inc.", ["rec-1"])],
        sectors=[_mention("Energy", ["rec-9"])],
    )

    graph = engine.build_graph(intelligence)

    node_ids = {node.id for node in graph.nodes}
    assert node_ids == {"company:Apple Inc.", "sector:Energy"}
    assert graph.edges == []


def test_node_types_are_tagged_correctly() -> None:
    engine = RelationshipEngine()
    intelligence = _intelligence(
        companies=[_mention("Apple Inc.", ["rec-1"])],
        sectors=[_mention("Technology", ["rec-1"])],
        countries=[_mention("United States", ["rec-1"])],
        themes=[_theme("earnings", ["rec-1"])],
    )

    graph = engine.build_graph(intelligence)

    types_by_id = {node.id: node.type for node in graph.nodes}
    assert types_by_id["company:Apple Inc."] == NodeType.COMPANY
    assert types_by_id["sector:Technology"] == NodeType.SECTOR
    assert types_by_id["country:United States"] == NodeType.COUNTRY
    assert types_by_id["theme:earnings"] == NodeType.THEME


def test_end_to_end_from_market_intelligence_engine_output() -> None:
    """Chains MarketIntelligenceEngine's real output into RelationshipEngine."""
    mi_engine = MarketIntelligenceEngine()
    records = [
        _record(
            id="rec-1",
            title="Apple reports record iPhone sales",
            text="Apple Inc. posted strong quarterly earnings driven by iPhone demand.",
        ),
        _record(
            id="rec-3",
            title="Apple and Tesla both surge on strong earnings",
            text="Shares of Apple and Tesla rallied after both reported strong quarterly earnings.",
        ),
    ]
    intelligence = mi_engine.analyze(records)

    graph = RelationshipEngine().build_graph(intelligence)

    company_to_company = [
        e for e in graph.edges if e.relationship_type == RelationshipType.COMPANY_TO_COMPANY
    ]
    assert len(company_to_company) == 1
    assert {company_to_company[0].source_id, company_to_company[0].target_id} == {
        "company:Apple Inc.",
        "company:Tesla Inc.",
    }
