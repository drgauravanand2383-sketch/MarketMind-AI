/**
 * Mirrors `app.global_markets.models`, `app.global_markets.ranked_asset`,
 * `app.global_markets.ranking.models`, `app.global_markets.ranking
 * .classification`, and `app.global_markets.intelligence_report` exactly
 * — the read-only `/api/v1/global-markets/*` REST surface
 * (`docs/architecture/GLOBAL_MARKET_INTELLIGENCE.md`) returns these
 * shapes verbatim, and the `GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED`
 * WebSocket event's payload is an `IntelligenceRun`.
 *
 * `MarketSessionContext` (attached to `CategoryRunOutcome` on the
 * backend) is deliberately not mirrored here — no page in this feature
 * renders per-category calendar detail, only the run-level
 * `IntelligenceRunStatus` and each category's own success/failure.
 */

export type MarketRegion = "INDIA" | "US" | "CHINA" | "FOREX" | "CRYPTO";

export type AssetClass = "EQUITY" | "FOREX" | "CRYPTO" | "PENNY_STOCK" | "MICROCAP_CRYPTO";

export type ReportCategory =
  | "INDIA_EQUITY"
  | "US_EQUITY"
  | "CHINA_EQUITY"
  | "FOREX"
  | "CRYPTO"
  | "INDIA_PENNY_STOCK"
  | "US_PENNY_STOCK"
  | "CHINA_PENNY_STOCK"
  | "LOW_CAP_CRYPTO";

export interface ReportCategoryDefinition {
  category: ReportCategory;
  market_region: MarketRegion;
  asset_class: AssetClass;
  top_n: number;
  display_name: string;
}

/** The five categories `GlobalMarketsResearchAgent` covers — mirrors
 * `app.global_markets.models.MAIN_REPORT_CATEGORIES`. */
export const MAIN_REPORT_CATEGORIES: ReportCategory[] = ["INDIA_EQUITY", "US_EQUITY", "CHINA_EQUITY", "FOREX", "CRYPTO"];

/** The four categories `PennyMicrocapIntelligenceAgent` covers — mirrors
 * `app.global_markets.models.PENNY_MICROCAP_REPORT_CATEGORIES`. */
export const PENNY_MICROCAP_REPORT_CATEGORIES: ReportCategory[] = [
  "INDIA_PENNY_STOCK",
  "US_PENNY_STOCK",
  "CHINA_PENNY_STOCK",
  "LOW_CAP_CRYPTO",
];

export type DataFreshnessStatus = "LIVE" | "PREVIOUS_CLOSE" | "STALE" | "UNAVAILABLE";

export interface DataProvenance {
  source_timestamp: string;
  retrieved_at: string;
  provider: string;
  data_freshness_status: DataFreshnessStatus;
}

export interface NormalizedAssetSnapshot {
  ticker: string;
  report_category: ReportCategory;
  name: string | null;
  price: number | null;
  currency: string | null;
  market_cap: number | null;
  fully_diluted_valuation: number | null;
  avg_daily_volume: number | null;
  avg_daily_traded_value: number | null;
  trading_history_days: number | null;
  is_suspended: boolean;
  is_delisted: boolean;
  bid_ask_spread_percent: number | null;
  provenance: DataProvenance;
}

export type RankingFactor =
  | "PRICE_PERFORMANCE"
  | "MOMENTUM"
  | "VOLUME_LIQUIDITY"
  | "VOLATILITY"
  | "MARKET_CAP"
  | "RISK"
  | "SOURCE_CONFIDENCE"
  | "DATA_FRESHNESS"
  | "CROSS_SOURCE_AGREEMENT"
  | "NEWS_EVENT_IMPACT"
  | "TECHNICAL_SIGNAL"
  | "FUNDAMENTAL_SIGNAL";

export interface FactorScore {
  factor: RankingFactor;
  value: number;
  explanation: string | null;
}

/** Never proof of fraud or manipulation — a momentum/risk label only.
 * See `app.global_markets.ranking.classification`'s own docstring. */
export type RiskClassification =
  | "STRONG_MOMENTUM_LOWER_RISK"
  | "STRONG_MOMENTUM_MODERATE_RISK"
  | "STRONG_MOMENTUM_HIGH_RISK"
  | "EXTREME_MOMENTUM_EXTREME_RISK"
  | "MODERATE_MOMENTUM"
  | "WEAK_MOMENTUM"
  | "INSUFFICIENT_CONFIDENCE";

export interface RankedAsset {
  run_id: string;
  category: ReportCategory;
  rank: number;
  final_score: number;
  factor_scores: FactorScore[];
  snapshot: NormalizedAssetSnapshot;
  /** Only populated for `PENNY_MICROCAP_REPORT_CATEGORIES` — `null` for
   * the five main categories. */
  risk_classification: RiskClassification | null;
}

export type IntelligenceRunStatus = "RUNNING" | "COMPLETED" | "PARTIAL" | "FAILED";

export interface CategoryRunOutcome {
  category: ReportCategory;
  succeeded: boolean;
  error: string | null;
}

export interface IntelligenceRun {
  id: string;
  run_date: string;
  status: IntelligenceRunStatus;
  category_outcomes: CategoryRunOutcome[];
  triggered_by: string;
  started_at: string;
  completed_at: string | null;
}

export interface AssetCommentary {
  ticker: string;
  rank: number;
  commentary: string;
}

export interface CategoryIntelligenceReport {
  run_id: string;
  category: ReportCategory;
  generated_at: string;
  overall_summary: string;
  asset_commentaries: AssetCommentary[];
  risk_note: string | null;
  provider: string;
  model: string;
}
