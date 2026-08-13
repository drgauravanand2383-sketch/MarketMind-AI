"""Relationship Engine — deterministic relationship extraction over MarketIntelligence.

RelationshipEngine.build_graph() detects Company→Sector, Company→Country,
Sector→Theme, Theme→Theme, and Company→Company relationships purely from
entities sharing supporting_record_ids already computed by
MarketIntelligenceEngine. No LLM call, no inference, and no prediction
occurs anywhere in this module — an edge is created only when two
entities' evidence sets intersect, and its weight is exactly the size of
that intersection.
"""

from __future__ import annotations

from itertools import combinations

from app.services.market_intelligence.models import EntityMention, MarketIntelligence, Theme
from app.services.relationship_engine.models import (
    GraphEdge,
    GraphNode,
    NodeType,
    RelationshipGraph,
    RelationshipType,
)

__all__ = ["RelationshipEngine"]


class RelationshipEngine:
    """Deterministically builds a RelationshipGraph from a MarketIntelligence summary."""

    def build_graph(self, intelligence: MarketIntelligence) -> RelationshipGraph:
        """Build a RelationshipGraph from `intelligence`.

        Args:
            intelligence: The MarketIntelligence to extract relationships from.

        Returns:
            A RelationshipGraph whose nodes are every detected company,
            sector, country, and theme, and whose edges are established
            only where two entities share at least one supporting record.
        """
        nodes = self._build_nodes(intelligence)

        edges: list[GraphEdge] = []
        edges.extend(
            self._cross_edges_entities(
                intelligence.companies,
                intelligence.sectors,
                NodeType.COMPANY,
                NodeType.SECTOR,
                RelationshipType.COMPANY_TO_SECTOR,
            )
        )
        edges.extend(
            self._cross_edges_entities(
                intelligence.companies,
                intelligence.countries,
                NodeType.COMPANY,
                NodeType.COUNTRY,
                RelationshipType.COMPANY_TO_COUNTRY,
            )
        )
        edges.extend(self._cross_edges_sector_theme(intelligence.sectors, intelligence.themes))
        edges.extend(self._pairwise_theme_edges(intelligence.themes))
        edges.extend(
            self._pairwise_entity_edges(
                intelligence.companies, NodeType.COMPANY, RelationshipType.COMPANY_TO_COMPANY
            )
        )

        return RelationshipGraph(nodes=nodes, edges=edges)

    def _node_id(self, node_type: NodeType, name: str) -> str:
        return f"{node_type.value}:{name}"

    def _build_nodes(self, intelligence: MarketIntelligence) -> list[GraphNode]:
        nodes: list[GraphNode] = []
        for mention in intelligence.companies:
            nodes.append(
                GraphNode(
                    id=self._node_id(NodeType.COMPANY, mention.name),
                    type=NodeType.COMPANY,
                    label=mention.name,
                )
            )
        for mention in intelligence.sectors:
            nodes.append(
                GraphNode(
                    id=self._node_id(NodeType.SECTOR, mention.name),
                    type=NodeType.SECTOR,
                    label=mention.name,
                )
            )
        for mention in intelligence.countries:
            nodes.append(
                GraphNode(
                    id=self._node_id(NodeType.COUNTRY, mention.name),
                    type=NodeType.COUNTRY,
                    label=mention.name,
                )
            )
        for theme in intelligence.themes:
            nodes.append(
                GraphNode(
                    id=self._node_id(NodeType.THEME, theme.keyword),
                    type=NodeType.THEME,
                    label=theme.keyword,
                )
            )
        return nodes

    def _cross_edges_entities(
        self,
        sources: list[EntityMention],
        targets: list[EntityMention],
        source_type: NodeType,
        target_type: NodeType,
        relationship_type: RelationshipType,
    ) -> list[GraphEdge]:
        """Create an edge for every source/target pair sharing >=1 supporting record."""
        edges: list[GraphEdge] = []
        for source in sources:
            source_ids = set(source.supporting_record_ids)
            for target in targets:
                shared = source_ids & set(target.supporting_record_ids)
                if not shared:
                    continue
                edges.append(
                    GraphEdge(
                        source_id=self._node_id(source_type, source.name),
                        target_id=self._node_id(target_type, target.name),
                        relationship_type=relationship_type,
                        weight=len(shared),
                        supporting_record_ids=sorted(shared),
                    )
                )
        return edges

    def _cross_edges_sector_theme(
        self, sectors: list[EntityMention], themes: list[Theme]
    ) -> list[GraphEdge]:
        """Create a Sector→Theme edge for every pair sharing >=1 supporting record."""
        edges: list[GraphEdge] = []
        for sector in sectors:
            sector_ids = set(sector.supporting_record_ids)
            for theme in themes:
                shared = sector_ids & set(theme.supporting_record_ids)
                if not shared:
                    continue
                edges.append(
                    GraphEdge(
                        source_id=self._node_id(NodeType.SECTOR, sector.name),
                        target_id=self._node_id(NodeType.THEME, theme.keyword),
                        relationship_type=RelationshipType.SECTOR_TO_THEME,
                        weight=len(shared),
                        supporting_record_ids=sorted(shared),
                    )
                )
        return edges

    def _pairwise_entity_edges(
        self, entities: list[EntityMention], node_type: NodeType, relationship_type: RelationshipType
    ) -> list[GraphEdge]:
        """Create an edge between every distinct pair of same-type entities sharing evidence."""
        edges: list[GraphEdge] = []
        for first, second in combinations(entities, 2):
            shared = set(first.supporting_record_ids) & set(second.supporting_record_ids)
            if not shared:
                continue
            edges.append(
                GraphEdge(
                    source_id=self._node_id(node_type, first.name),
                    target_id=self._node_id(node_type, second.name),
                    relationship_type=relationship_type,
                    weight=len(shared),
                    supporting_record_ids=sorted(shared),
                )
            )
        return edges

    def _pairwise_theme_edges(self, themes: list[Theme]) -> list[GraphEdge]:
        """Create a Theme→Theme edge between every distinct pair of co-occurring themes."""
        edges: list[GraphEdge] = []
        for first, second in combinations(themes, 2):
            shared = set(first.supporting_record_ids) & set(second.supporting_record_ids)
            if not shared:
                continue
            edges.append(
                GraphEdge(
                    source_id=self._node_id(NodeType.THEME, first.keyword),
                    target_id=self._node_id(NodeType.THEME, second.keyword),
                    relationship_type=RelationshipType.THEME_TO_THEME,
                    weight=len(shared),
                    supporting_record_ids=sorted(shared),
                )
            )
        return edges
