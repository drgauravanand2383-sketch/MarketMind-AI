"""NewsCollectorAgent (AGT-003): collects and normalizes news from providers."""

from app.agents.news_collector.agent import NewsCollectorAgent
from app.agents.news_collector.models import (
    NewsCollectionRequest,
    NewsCollectionResult,
    NewsItem,
    ProviderRunSummary,
)

__all__ = [
    "NewsCollectorAgent",
    "NewsCollectionRequest",
    "NewsCollectionResult",
    "NewsItem",
    "ProviderRunSummary",
]
