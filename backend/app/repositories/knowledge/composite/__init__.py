"""Composite Knowledge Repository: coordinates PostgreSQL and ChromaDB behind one interface."""

from app.repositories.knowledge.composite.repository import CompositeKnowledgeRepository

__all__ = ["CompositeKnowledgeRepository"]
