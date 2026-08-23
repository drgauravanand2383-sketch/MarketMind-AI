"""Shared helpers for Portfolio Recommendation Engine tests."""

from __future__ import annotations

from datetime import UTC, datetime

from app.agents.company_research.models import (
    CompanyOverview,
    CompanyResearchReport,
    CompanyResearchRequest,
    ConfidenceSummary,
    MarketIntelligenceSummary,
)
from app.agents.portfolio_intelligence.models import CompanySummary
from app.alerts.models import Alert, AlertPriority, AlertStatus, NotificationChannel
from app.recommendations.models import CandidateEvidence
from app.screening.models import ScreenResult
from app.signals.models import SignalCategory, SignalPriority, SignalResult

NOW = datetime(2026, 8, 9, tzinfo=UTC)


def make_signal(
    ticker: str = "AAPL",
    score: float = 80.0,
    triggered: bool = True,
    priority: SignalPriority = SignalPriority.HIGH,
    confidence: float = 90.0,
) -> SignalResult:
    return SignalResult(
        ticker=ticker, company_name=ticker, signal_name="Momentum", category=SignalCategory.MOMENTUM,
        triggered=triggered, confidence=confidence, score=score, priority=priority, reason="matched",
        timestamp=NOW,
    )


def make_alert(
    ticker: str = "AAPL",
    score: float = 80.0,
    status: AlertStatus = AlertStatus.GENERATED,
    alert_id: str = "a1",
) -> Alert:
    return Alert(
        id=alert_id, rule_id="r1", ticker=ticker, signal_name="Momentum", priority=AlertPriority.HIGH,
        status=status, reason="matched", confidence=90.0, score=score,
        eligible_channels=(NotificationChannel.EMAIL,), created_at=NOW,
    )


def make_screen_result(ticker: str = "AAPL", score: float = 80.0, passed: bool = True) -> ScreenResult:
    return ScreenResult(ticker=ticker, passed=passed, score=score)


def make_research_report(ticker: str = "AAPL", confidence: float = 0.9) -> CompanyResearchReport:
    return CompanyResearchReport(
        request=CompanyResearchRequest(company_name=ticker, ticker=ticker),
        generated_at=NOW,
        company_overview=CompanyOverview(
            company_name=ticker, ticker=ticker, matched=True, entity_recognized=True, mention_count=1
        ),
        market_intelligence=MarketIntelligenceSummary(mention_count=1),
        confidence_summary=ConfidenceSummary(overall_confidence=confidence, supporting_record_count=1, basis="x"),
    )


def make_portfolio_summary(ticker: str = "AAPL", confidence: float = 0.9) -> CompanySummary:
    return CompanySummary(
        company_name=ticker, ticker=ticker, resolved_company_name=ticker, matched=True,
        entity_recognized=True, overall_confidence=confidence,
    )


def make_evidence(ticker: str = "AAPL", **overrides: object) -> CandidateEvidence:
    defaults: dict[str, object] = {"ticker": ticker}
    defaults.update(overrides)
    return CandidateEvidence(**defaults)
