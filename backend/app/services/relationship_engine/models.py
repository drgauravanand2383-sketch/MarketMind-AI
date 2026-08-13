"""Schemas for the Relationship Engine.

RelationshipGraph is produced entirely through deterministic co-occurrence
rules over an already-computed MarketIntelligence — no LLM, no inference,
and no prediction occurs anywhere in this engine.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["NodeType", "RelationshipType", "GraphNode", "GraphEdge", "RelationshipGraph"]


class NodeType(str, Enum):
    """The category of entity a graph node represents."""

    COMPANY = "company"
    SECTOR = "sector"
    COUNTRY = "country"
    THEME = "theme"


class RelationshipType(str, Enum):
    """The kind of relationship a graph edge represents."""

    COMPANY_TO_SECTOR = "company_to_sector"
    COMPANY_TO_COUNTRY = "company_to_country"
    SECTOR_TO_THEME = "sector_to_theme"
    THEME_TO_THEME = "theme_to_theme"
    COMPANY_TO_COMPANY = "company_to_company"


class GraphNode(BaseModel):
    """A single entity node in the relationship graph."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: NodeType
    label: str


class GraphEdge(BaseModel):
    """A relationship between two nodes, evidenced by shared supporting records."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    target_id: str
    relationship_type: RelationshipType
    weight: int
    supporting_record_ids: list[str] = Field(default_factory=list)


class RelationshipGraph(BaseModel):
    """The output of RelationshipEngine.build_graph(): a graph structure only."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
