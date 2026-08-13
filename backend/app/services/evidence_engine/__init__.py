"""Evidence Engine: deterministic evidence extraction and organization.

Every EvidenceItem is traceable to exactly one KnowledgeRecord. No
reasoning, LLM, summarization, prediction, or storage occurs here — this
package builds evidence references only.
"""

from app.services.evidence_engine.engine import EvidenceEngine
from app.services.evidence_engine.models import EvidenceGraph, EvidenceItem

__all__ = ["EvidenceEngine", "EvidenceGraph", "EvidenceItem"]
