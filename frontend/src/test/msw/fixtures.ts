import type { MetadataResponse, SuccessResponse } from "@/types/api";
import type { AuthenticationResponse, User } from "@/types/auth";
import type { DetectedChange } from "@/types/continuous-intelligence";
import type { ApplicationHealth, ReadinessStatus, VersionResponse } from "@/types/health";
import type { Watchlist, WatchlistItem, WatchlistStatistics } from "@/types/watchlist";
import type { InitialAnalysisState, MarketDataRefreshResult, PortfolioIntelligenceReport, RecommendationCandidate, RecommendationResult, RiskAssessment } from "@/types/portfolio";
import type { CompanyResearchReport } from "@/types/research";
import type { ScreenFilter, ScreeningProfile, ScreenResult } from "@/types/screening";
import type { Alert } from "@/types/alerts";
import type { InvestmentStrategy, StrategyEvaluationResult } from "@/types/strategy";
import type { MarketDataSnapshot, SignalDefinition, SignalResult } from "@/types/signals";
import type { BacktestPeriod, BacktestResult, BacktestRun, HistoricalSnapshot } from "@/types/backtesting";
import type { ContributionBreakdown, ExplainabilityResult } from "@/types/explainability";

export function buildMeta(): MetadataResponse {
  return { request_id: "test-request-id", timestamp: new Date().toISOString(), api_version: "v1" };
}

export function wrapSuccess<T>(data: T): SuccessResponse<T> {
  return { data, meta: buildMeta() };
}

export const testUser: User = {
  id: "11111111-1111-1111-1111-111111111111",
  username: "alice",
  email: "alice@example.com",
  display_name: "Alice",
  status: "ACTIVE",
  roles: ["analyst"],
  permissions: ["portfolio:read"],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

export function buildAuthenticationResponse(overrides?: Partial<AuthenticationResponse>): AuthenticationResponse {
  const now = Date.now();
  return {
    access_token: {
      token: "test-access-token",
      token_type: "access",
      subject: testUser.id,
      token_id: "access-token-id",
      issued_at: new Date(now).toISOString(),
      expires_at: new Date(now + 15 * 60_000).toISOString(),
    },
    refresh_token: {
      token: "test-refresh-token",
      subject: testUser.id,
      token_id: "refresh-token-id",
      issued_at: new Date(now).toISOString(),
      expires_at: new Date(now + 7 * 24 * 60 * 60_000).toISOString(),
    },
    user: testUser,
    ...overrides,
  };
}

export const testApplicationHealth: ApplicationHealth = {
  state: "HEALTHY",
  repositories: [{ name: "postgres", state: "HEALTHY", message: "Connected." }],
  services: [{ name: "authentication", state: "HEALTHY", message: "Operational." }],
  dependencies: [{ name: "chromadb", state: "HEALTHY", message: "Reachable." }],
  checked_at: "2026-01-01T00:00:00Z",
  summary: "All systems operational.",
};

export const testReadiness: ReadinessStatus = {
  ready: true,
  application_health: testApplicationHealth,
  blocking_issues: [],
};

export const testVersion: VersionResponse = {
  api_version: "v1",
  application_version: "1.0.0",
  environment: "test",
};

export function buildWatchlistItem(overrides: Partial<WatchlistItem> = {}): WatchlistItem {
  return {
    ticker: "AAPL",
    company_name: "Apple Inc.",
    country: "US",
    sector: "Technology",
    theme: "AI",
    source_agent: null,
    confidence: 0.82,
    reason: null,
    added_at: "2026-01-01T00:00:00Z",
    notes: null,
    ...overrides,
  };
}

export function buildWatchlist(overrides: Partial<Watchlist> = {}): Watchlist {
  return {
    id: "test-watchlist-1",
    name: "Tech Growth",
    description: "High-growth technology companies.",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    items: [buildWatchlistItem()],
    ...overrides,
  };
}

export const testWatchlistStatistics: WatchlistStatistics = {
  watchlist_id: "test-watchlist-1",
  total_companies: 1,
  average_confidence: 0.82,
  top_sectors: ["Technology"],
  sector_distribution: { Technology: 1 },
  country_distribution: { US: 1 },
  theme_distribution: { AI: 1 },
};

export const testRiskAssessment: RiskAssessment = {
  request_id: "risk-1",
  overall_risk_score: 42,
  overall_severity: "MODERATE",
  risk_metrics: [
    {
      metric_name: "Sector concentration",
      category: "SECTOR",
      value: 0.6,
      score: 55,
      severity: "MODERATE",
      description: "Technology makes up 60% of holdings.",
    },
    {
      metric_name: "Sector Diversification",
      category: "DIVERSIFICATION",
      value: 0.4,
      score: 60,
      severity: "MODERATE",
      description: "Holdings span 3 sectors.",
    },
    {
      metric_name: "Holding Concentration",
      category: "CONCENTRATION",
      value: 0.5,
      score: 50,
      severity: "MODERATE",
      description: "Top holding is 50% of the portfolio.",
    },
    {
      metric_name: "Liquidity Proxy",
      category: "LIQUIDITY",
      value: 0.7,
      score: 70,
      severity: "LOW",
      description: "Holdings are broadly liquid.",
    },
    {
      metric_name: "Volatility Proxy",
      category: "VOLATILITY",
      value: 0.3,
      score: 35,
      severity: "MODERATE",
      description: "Moderate score dispersion across holdings.",
    },
  ],
  exposures: [
    { sector: "Technology", country: null, industry: null, weight: 0.6, holding_count: 3 },
    { sector: "Healthcare", country: null, industry: null, weight: 0.4, holding_count: 2 },
    { sector: null, country: "US", industry: null, weight: 0.8, holding_count: 4 },
    { sector: null, country: "DE", industry: null, weight: 0.2, holding_count: 1 },
  ],
  recommendations: ["Diversify away from Technology."],
  summary: "Moderate concentration risk in Technology.",
  market_data_coverage: {
    status: "PARTIAL",
    fresh_count: 1,
    stale_count: 0,
    unavailable_count: 0,
    not_evaluated_count: 2,
    total_candidates: 3,
  },
  generated_at: "2026-01-03T00:00:00Z",
};

export function buildSignalResult(overrides: Partial<SignalResult> = {}): SignalResult {
  return {
    ticker: "AAPL",
    company_name: "Apple Inc.",
    signal_name: "RSI Oversold",
    category: "TECHNICAL",
    triggered: true,
    confidence: 88,
    score: 82,
    priority: "HIGH",
    matched_conditions: [{ condition_id: "c1", field: "quote.price", operator: "GREATER_THAN", weight: 1, passed: true, reason: null }],
    failed_conditions: [],
    reason: "RSI below 30 threshold.",
    timestamp: "2026-01-03T00:00:00Z",
    ...overrides,
  };
}

export function buildAlert(overrides: Partial<Alert> = {}): Alert {
  return {
    id: "alert-1",
    rule_id: "rule-1",
    ticker: "AAPL",
    company_name: "Apple Inc.",
    signal_name: "RSI Oversold",
    alert_type: "SIGNAL_TRIGGERED",
    priority: "HIGH",
    status: "GENERATED",
    reason: "RSI Oversold triggered with high confidence.",
    confidence: 88,
    score: 82,
    eligible_channels: ["IN_APP"],
    created_at: "2026-01-03T00:00:00Z",
    ...overrides,
  };
}

export function buildRecommendationCandidate(overrides: Partial<RecommendationCandidate> = {}): RecommendationCandidate {
  return {
    ticker: "AAPL",
    company_name: "Apple Inc.",
    country: "US",
    sector: "Technology",
    industry: "Consumer Electronics",
    overall_score: 82,
    confidence: 78,
    recommendation: "STRONG_BUY",
    reasoning: "Strong evidence across screening and research.",
    supporting_signals: [buildSignalResult()],
    supporting_alerts: [buildAlert()],
    screening_score: 90,
    planning_score: null,
    research_score: 80,
    portfolio_score: 75,
    signal_score: 82,
    alert_score: 82,
    created_at: "2026-01-03T00:00:00Z",
    ...overrides,
  };
}

export const testRecommendationResult: RecommendationResult = {
  request_id: "rec-1",
  generated_at: "2026-01-03T00:00:00Z",
  total_candidates: 3,
  recommendations: [
    buildRecommendationCandidate({
      market_price: 195.5,
      market_change_percent: 1.25,
      market_freshness: "FRESH",
      market_contribution: "direct",
    }),
    buildRecommendationCandidate({
      ticker: "MSFT",
      company_name: "Microsoft",
      sector: "Technology",
      overall_score: 65,
      confidence: 60,
      recommendation: "WATCH",
      supporting_signals: [],
      supporting_alerts: [],
    }),
    buildRecommendationCandidate({
      ticker: "JNJ",
      company_name: "Johnson & Johnson",
      country: "US",
      sector: "Healthcare",
      industry: "Pharmaceuticals",
      overall_score: 58,
      confidence: 55,
      recommendation: "BUY",
      reasoning: "Steady dividend history with moderate growth.",
      supporting_signals: [],
      supporting_alerts: [],
    }),
  ],
  summary: { strong_buy: 1, buy: 1, watch: 1, hold: 0, avoid: 0, average_score: 68.3, average_confidence: 64.3 },
};

export function buildRecommendationResult(overrides: Partial<RecommendationResult> = {}): RecommendationResult {
  return { ...testRecommendationResult, ...overrides };
}

export function buildRiskAssessment(overrides: Partial<RiskAssessment> = {}): RiskAssessment {
  return { ...testRiskAssessment, ...overrides };
}

export const testInitialAnalysisState: InitialAnalysisState = {
  portfolio_id: "wl-1",
  status: "UNAVAILABLE",
  detail: "No companies tracked yet.",
  recommendation_request_id: null,
  risk_request_id: null,
  started_at: null,
  completed_at: null,
};

export function buildInitialAnalysisState(overrides: Partial<InitialAnalysisState> = {}): InitialAnalysisState {
  return { ...testInitialAnalysisState, ...overrides };
}

export function buildDetectedChange(overrides: Partial<DetectedChange> = {}): DetectedChange {
  return {
    fingerprint: "MARKET:dell:price",
    domain: "MARKET",
    entity_id: "dell",
    label: "Dell",
    priority: "HIGH",
    summary: "Dell moved up 5.2% to $500.00.",
    previous_value: "475.00",
    current_value: "500.00",
    portfolio_id: null,
    detected_at: "2026-08-15T00:00:00Z",
    ...overrides,
  };
}

export function buildMarketDataRefreshResult(overrides: Partial<MarketDataRefreshResult> = {}): MarketDataRefreshResult {
  return {
    execution_id: "exec-1",
    started_at: "2026-08-15T00:00:00Z",
    completed_at: "2026-08-15T00:00:05Z",
    entities_requested: 12,
    fresh_count: 12,
    stale_count: 0,
    unavailable_count: 0,
    results: [],
    ...overrides,
  };
}

export function buildStrategyEvaluationResult(overrides: Partial<StrategyEvaluationResult> = {}): StrategyEvaluationResult {
  return {
    request_id: "test-strategy-eval-1",
    evaluated_at: "2026-01-03T00:00:00Z",
    overall_alignment: 72,
    best_strategy: "Momentum Growth",
    strategy_matches: [
      {
        strategy_id: "strategy-1",
        strategy_name: "Momentum Growth",
        alignment_score: 72,
        confidence: 80,
        matched_rules: [{ rule_id: "rule-1", field: "overall_score", operator: "GREATER_THAN", weight: 1, pass_rate: 0.8, evaluated_candidate_count: 3, reason: "2 of 3 candidates satisfied this rule." }],
        failed_rules: [],
        reasoning: "Momentum Growth scored 72 alignment across 3 candidates.",
      },
    ],
    summary: { total_strategies: 1, best_alignment: 72, average_alignment: 72, highest_confidence: 80 },
    ...overrides,
  };
}

export function buildInvestmentStrategy(overrides: Partial<InvestmentStrategy> = {}): InvestmentStrategy {
  return {
    id: "strategy-1",
    name: "Momentum Growth",
    description: "Favors high-momentum, high-confidence candidates.",
    strategy_type: "MOMENTUM",
    enabled: true,
    weightings: {
      overall_score: 1,
      screening_score: 1,
      planning_score: 1,
      research_score: 1,
      portfolio_score: 1,
      signal_score: 1,
      alert_score: 1,
    },
    rules: [{ id: "rule-1", field: "overall_score", operator: "GREATER_THAN", value: 60, weight: 1, enabled: true }],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    ...overrides,
  };
}

export function buildSignalDefinition(overrides: Partial<SignalDefinition> = {}): SignalDefinition {
  return {
    id: "definition-1",
    name: "RSI Oversold",
    description: "Flags companies with an oversold RSI reading.",
    category: "TECHNICAL",
    enabled: true,
    priority: "HIGH",
    conditions: [{ id: "c1", field: "quote.price", operator: "GREATER_THAN", value: 100, weight: 1, group: null, enabled: true }],
    groups: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    ...overrides,
  };
}

export function buildMarketDataSnapshot(overrides: Partial<MarketDataSnapshot> = {}): MarketDataSnapshot {
  return {
    ticker: "AAPL",
    company_name: "Apple Inc.",
    quote: { ticker: "AAPL", price: 150, timestamp: "2026-01-03T00:00:00Z" },
    ...overrides,
  };
}

export function buildResearchReport(overrides: Partial<CompanyResearchReport> = {}): CompanyResearchReport {
  return {
    request: { company_name: "Apple Inc.", ticker: "AAPL", include_relationships: true, include_evidence: true },
    generated_at: "2026-01-04T00:00:00Z",
    company_overview: {
      company_name: "Apple Inc.",
      ticker: "AAPL",
      matched: true,
      entity_recognized: true,
      mention_count: 12,
      supporting_record_ids: ["rec-1"],
    },
    latest_news: [{ record_id: "rec-1", title: "Apple announces new product", url: "https://example.com/news", published_at: "2026-01-02T00:00:00Z", source: "Example Wire" }],
    market_intelligence: { mention_count: 12, group_confidence: 0.7, supporting_record_ids: ["rec-1"] },
    relationship_analysis: [{ related_id: "rel-1", related_label: "Foxconn", relationship_type: "SUPPLIER", weight: 5 }],
    sector_analysis: [{ sector: "Technology", weight: 8 }],
    country_exposure: [{ country: "US", weight: 10 }],
    theme_analysis: [{ keyword: "AI", occurrence_count: 4 }],
    supporting_evidence: [{ record_id: "rec-1", source: "Example Wire", provider: "wire", url: "https://example.com/news", published_at: "2026-01-02T00:00:00Z", title: "Apple announces new product" }],
    confidence_summary: { overall_confidence: 0.82, supporting_record_count: 12, basis: "evidence-weighted" },
    key_risks: [],
    narrative: { summary: "Apple shows strong evidence coverage.", key_findings: ["Consistent supplier relationships."], risk_commentary: null },
    ...overrides,
  };
}

export function buildScreenFilter(overrides: Partial<ScreenFilter> = {}): ScreenFilter {
  return { id: "filter-1", field: "market_cap", operator: "GREATER_THAN", value: 1_000_000, group: null, enabled: true, ...overrides };
}

export function buildScreeningProfile(overrides: Partial<ScreeningProfile> = {}): ScreeningProfile {
  return {
    id: "test-profile-1",
    name: "Large Cap",
    description: "Large market-cap companies.",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    is_default: false,
    filters: [buildScreenFilter()],
    groups: [],
    ...overrides,
  };
}

export function buildScreenResult(overrides: Partial<ScreenResult> = {}): ScreenResult {
  return {
    ticker: "AAPL",
    company_name: "Apple Inc.",
    passed: true,
    matched_filters: [{ filter_id: "filter-1", field: "market_cap", operator: "GREATER_THAN", passed: true, reason: null }],
    failed_filters: [],
    score: 100,
    details: { total_filters: 1, enabled_filters: 1, disabled_filters: 0 },
    ...overrides,
  };
}

export function buildHistoricalSnapshot(overrides: Partial<HistoricalSnapshot> = {}): HistoricalSnapshot {
  return {
    timestamp: "2026-01-15T00:00:00Z",
    recommendation_result_id: "rec-1",
    strategy_evaluation_id: null,
    risk_assessment_id: null,
    benchmark_value: 100_500,
    ...overrides,
  };
}

export function buildBacktestPeriod(overrides: Partial<BacktestPeriod> = {}): BacktestPeriod {
  return {
    timestamp: "2026-01-15T00:00:00Z",
    portfolio_value: 104_000,
    benchmark_value: 101_500,
    return_percent: 4,
    notes: "Period 1",
    ...overrides,
  };
}

export function buildBacktestRun(overrides: Partial<BacktestRun> = {}): BacktestRun {
  return {
    request_id: "test-backtest-1",
    started_at: "2026-02-01T00:00:00Z",
    completed_at: "2026-02-01T00:05:00Z",
    status: "COMPLETED",
    processed_snapshots: 1,
    results: [buildBacktestPeriod()],
    ...overrides,
  };
}

export function buildBacktestResult(overrides: Partial<BacktestResult> = {}): BacktestResult {
  return {
    request_id: "test-backtest-1",
    portfolio_return: 4,
    benchmark_return: 1.5,
    excess_return: 2.5,
    max_drawdown: 3.2,
    win_rate: 100,
    total_periods: 1,
    successful_periods: 1,
    failed_periods: 0,
    summary: "Backtest completed with 1 period.",
    generated_at: "2026-02-01T00:05:00Z",
    ...overrides,
  };
}

export function buildContributionBreakdown(overrides: Partial<ContributionBreakdown> = {}): ContributionBreakdown {
  return {
    source: "Technology",
    category: "SECTOR",
    weight: 0.6,
    contribution_percent: 3.1,
    description: "Technology contributed 3.1%.",
    ...overrides,
  };
}

export function buildExplainabilityResult(overrides: Partial<ExplainabilityResult> = {}): ExplainabilityResult {
  return {
    request_id: "test-explainability-1",
    generated_at: "2026-02-01T00:05:00Z",
    recommendation_explanations: [
      {
        ticker: "AAPL",
        company_name: "Apple Inc.",
        overall_score: 82,
        confidence: 78,
        contributing_components: [buildContributionBreakdown({ source: "screening_score", category: "SCREENING", contribution_percent: 30 })],
        top_positive_factors: [buildContributionBreakdown({ source: "screening_score", category: "SCREENING", contribution_percent: 30 })],
        top_negative_factors: [buildContributionBreakdown({ source: "alert_score", category: "ALERTS", contribution_percent: -5 })],
        reasoning: "Strong evidence across screening and research.",
        summary: "AAPL scored well due to consistent screening and research signals.",
      },
    ],
    strategy_explanations: [],
    risk_explanation: null,
    performance_attribution: null,
    overall_summary: "Explanation generated from recommendation result rec-1.",
    ...overrides,
  };
}

export const testPortfolioIntelligenceReport: PortfolioIntelligenceReport = {
  request: null,
  generated_at: "2026-01-03T00:00:00Z",
  executive_summary: "A concentrated technology portfolio with strong momentum.",
  portfolio_overview: { portfolio_name: "Tech Growth", holding_count: 1, matched_holding_count: 1, generated_at: "2026-01-03T00:00:00Z" },
  company_summaries: [],
  sector_exposure: [{ sector: "Technology", company_names: ["Apple Inc."], total_weight: 100, is_shared: false }],
  concentration_observations: ["Heavily weighted toward Technology."],
  relationship_observations: [],
  notable_market_events: [],
  evidence_summary: [],
  data_quality_notes: [],
  market_snapshot: {
    portfolio_id: "wl-1",
    generated_at: "2026-01-03T00:00:00Z",
    company_snapshots: [
      {
        entity_id: "netflix",
        status: "FRESH",
        snapshot: {
          entity_id: "netflix",
          canonical_name: "Netflix Inc.",
          ticker: "NFLX",
          exchange: "NASDAQ",
          currency: "USD",
          price: 610.25,
          previous_close: 605.0,
          change: 5.25,
          change_percent: 0.87,
          day_high: 612.0,
          day_low: 604.5,
          volume: 3_000_000,
          quoted_at: "2026-01-03T00:00:00Z",
          fetched_at: "2026-01-03T00:00:00Z",
          provider: "Yahoo Finance",
          trading_status: null,
        },
        reason: "ok",
      },
    ],
    valuation_status: "VALUATION_UNAVAILABLE",
    valuation_unavailable_reason: "No holdings quantity/position-size data exists for this portfolio.",
    fresh_count: 1,
    stale_count: 0,
    unavailable_count: 0,
    entity_not_mapped_count: 0,
  },
};
