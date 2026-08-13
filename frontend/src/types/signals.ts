/**
 * Mirrors `app.signals.models` and `app.market_data.models` field-for-field
 * (verified against the actual backend source, Frontend Milestone 5).
 * `SignalCondition.field` is a dotted `"<namespace>.<field>"` path into one
 * of four Market Data Abstraction Layer models (`quote`/`profile`/
 * `fundamentals`/`ratios`) — never a flat field name, unlike Screening's
 * `CompanyMetrics`. Signal Detection has no portfolio concept at all:
 * `POST /signals/evaluate` takes caller-supplied `MarketDataSnapshot[]`
 * directly, never reading from a watchlist/portfolio.
 */

export type SignalOperator =
  | "EQUALS"
  | "NOT_EQUALS"
  | "GREATER_THAN"
  | "GREATER_EQUAL"
  | "LESS_THAN"
  | "LESS_EQUAL"
  | "BETWEEN"
  | "IN"
  | "NOT_IN";

export const SIGNAL_OPERATORS: SignalOperator[] = [
  "EQUALS",
  "NOT_EQUALS",
  "GREATER_THAN",
  "GREATER_EQUAL",
  "LESS_THAN",
  "LESS_EQUAL",
  "BETWEEN",
  "IN",
  "NOT_IN",
];

export type SignalLogicType = "AND" | "OR";

export type SignalCategory = "TECHNICAL" | "FUNDAMENTAL" | "VALUATION" | "QUALITY" | "MOMENTUM" | "VOLUME" | "VOLATILITY" | "CUSTOM";

export const SIGNAL_CATEGORIES: SignalCategory[] = [
  "TECHNICAL",
  "FUNDAMENTAL",
  "VALUATION",
  "QUALITY",
  "MOMENTUM",
  "VOLUME",
  "VOLATILITY",
  "CUSTOM",
];

export type SignalPriority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export const SIGNAL_PRIORITIES: SignalPriority[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

export interface SignalConditionGroup {
  id: string;
  logic: SignalLogicType;
  parent_group?: string | null;
}

export interface SignalCondition {
  id: string;
  /** `"<namespace>.<field>"`, namespace one of `quote`/`profile`/`fundamentals`/`ratios`. */
  field: string;
  operator: SignalOperator;
  value: unknown;
  weight: number;
  group?: string | null;
  enabled: boolean;
}

export interface SignalDefinition {
  id: string;
  name: string;
  description: string;
  category: SignalCategory;
  enabled: boolean;
  priority: SignalPriority;
  conditions: SignalCondition[];
  groups: SignalConditionGroup[];
  created_at: string;
  updated_at: string;
}

export interface CreateSignalDefinitionRequest {
  name: string;
  description?: string;
  category?: SignalCategory;
  priority?: SignalPriority;
  enabled?: boolean;
  conditions?: SignalCondition[];
  groups?: SignalConditionGroup[];
}

export interface ListSignalDefinitionsParams {
  page?: number;
  page_size?: number;
  sort?: "name" | "created_at" | "updated_at";
  direction?: "asc" | "desc";
  [key: string]: string | number | undefined;
}

export type Currency = "USD" | "EUR" | "GBP" | "JPY" | "CNY" | "INR" | "CAD" | "AUD" | "CHF" | "HKD" | "SGD" | "KRW" | "BRL";

export type Exchange =
  | "NYSE"
  | "NASDAQ"
  | "AMEX"
  | "LSE"
  | "NSE"
  | "BSE"
  | "TSE"
  | "HKEX"
  | "SSE"
  | "SZSE"
  | "TSX"
  | "ASX"
  | "EURONEXT"
  | "OTHER";

/** Namespace `quote.*`. */
export interface MarketQuote {
  ticker: string;
  price: number;
  timestamp: string;
  change?: number | null;
  change_percent?: number | null;
  volume?: number | null;
  average_volume?: number | null;
  previous_close?: number | null;
  open?: number | null;
  day_high?: number | null;
  day_low?: number | null;
  currency?: Currency | null;
  exchange?: Exchange | null;
}

/** Namespace `profile.*`. */
export interface CompanyProfile {
  ticker: string;
  company_name: string;
  exchange?: Exchange | null;
  country?: string | null;
  sector?: string | null;
  industry?: string | null;
  description?: string | null;
  website?: string | null;
  employees?: number | null;
  ipo_date?: string | null;
  currency?: Currency | null;
  market_cap?: number | null;
  shares_outstanding?: number | null;
}

/** Namespace `ratios.*` — every field optional, real-world coverage is always partial. */
export interface FinancialRatios {
  pe?: number | null;
  forward_pe?: number | null;
  pb?: number | null;
  ps?: number | null;
  peg?: number | null;
  ev_ebitda?: number | null;
  roe?: number | null;
  roa?: number | null;
  roic?: number | null;
  gross_margin?: number | null;
  operating_margin?: number | null;
  net_margin?: number | null;
  current_ratio?: number | null;
  quick_ratio?: number | null;
  debt_equity?: number | null;
  interest_coverage?: number | null;
  cash_ratio?: number | null;
  free_cash_flow?: number | null;
}

/** Namespace `fundamentals.*` — every field optional, real-world coverage is always partial. */
export interface Fundamentals {
  revenue?: number | null;
  gross_profit?: number | null;
  operating_income?: number | null;
  net_income?: number | null;
  ebitda?: number | null;
  eps?: number | null;
  book_value?: number | null;
  cash?: number | null;
  debt?: number | null;
  assets?: number | null;
  liabilities?: number | null;
  equity?: number | null;
  cash_flow?: number | null;
}

/** One company's bundle of already-fetched Market Data records — every
 * source is optional; a condition referencing a missing source fails that
 * condition (the same "missing data" convention `CompanyMetrics` uses). */
export interface MarketDataSnapshot {
  ticker: string;
  company_name?: string | null;
  quote?: MarketQuote | null;
  profile?: CompanyProfile | null;
  fundamentals?: Fundamentals | null;
  ratios?: FinancialRatios | null;
}

export interface ConditionEvaluation {
  condition_id: string;
  field: string;
  operator: SignalOperator;
  weight: number;
  passed: boolean;
  reason: string | null;
}

export interface SignalResult {
  ticker: string;
  company_name: string | null;
  signal_name: string;
  category: SignalCategory;
  triggered: boolean;
  confidence: number;
  score: number;
  priority: SignalPriority;
  matched_conditions: ConditionEvaluation[];
  failed_conditions: ConditionEvaluation[];
  reason: string;
  timestamp: string;
}

export interface SignalBatchResult {
  signals: SignalResult[];
  evaluated: number;
  triggered: number;
  average_score: number;
  summary: string;
}

export interface EvaluateSignalsRequest {
  definition_id: string;
  snapshots: MarketDataSnapshot[];
}

/** `result_id` is the HTTP-layer cache key (in-memory, lost on backend
 * restart, no server-side aggregation across multiple evaluate calls). */
export interface SignalEvaluationEnvelope {
  result_id: string;
  definition_id: string;
  batch_result: SignalBatchResult;
}
