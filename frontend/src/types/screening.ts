/**
 * Mirrors `app.screening.models` and `app.api.v1.screening.schemas`
 * field-for-field (verified against the actual backend source, Frontend
 * Milestone 4). Screening PROFILES are durably persisted (Postgres,
 * via `PostgresScreeningRepository`) — unlike Company Research and
 * Screening RUN RESULTS, which are in-memory only (`InMemoryResultStore`,
 * lost on restart, see `docs/architecture/INTELLIGENCE_API.md` §2).
 * Profiles have no owner/user_id field — they are not per-user scoped.
 */

export type ScreenOperator =
  | "EQUALS"
  | "NOT_EQUALS"
  | "GREATER_THAN"
  | "GREATER_EQUAL"
  | "LESS_THAN"
  | "LESS_EQUAL"
  | "BETWEEN"
  | "IN"
  | "NOT_IN";

export const SCREEN_OPERATORS: ScreenOperator[] = [
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

export type LogicType = "AND" | "OR";

/** `value` shape depends on `operator`: scalar for most, `[low, high]`
 * for BETWEEN, a non-empty array for IN/NOT_IN. */
export interface ScreenFilter {
  id: string;
  field: string;
  operator: ScreenOperator;
  value: unknown;
  group?: string | null;
  enabled: boolean;
}

/** Forms a tree via `parent_group` — cycles are rejected server-side by
 * a pydantic `model_validator`; the builder UI must not allow creating one. */
export interface LogicalGroup {
  id: string;
  logic: LogicType;
  parent_group?: string | null;
}

/** `description` defaults to `""` on the backend (`ScreeningProfile.description: str = ""`)
 * — never `null`, unlike `Watchlist.description`. */
export interface ScreeningProfile {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  is_default: boolean;
  filters: ScreenFilter[];
  groups: LogicalGroup[];
}

export interface CreateScreeningProfileRequest {
  name: string;
  description?: string;
  is_default?: boolean;
  filters?: ScreenFilter[];
  groups?: LogicalGroup[];
}

/** `description: string | null` here only because `UpdateScreeningProfileRequest`
 * declares it nullable on the backend — callers on this frontend should
 * never actually send `null` (the merged `ScreeningProfile.description`
 * is non-nullable and would fail backend validation). */
export interface UpdateScreeningProfileRequest {
  name?: string;
  description?: string | null;
  is_default?: boolean;
  filters?: ScreenFilter[];
  groups?: LogicalGroup[];
}

/** Frontend Milestone 4 addition — wraps the pre-existing
 * `ScreeningEngine.duplicate_profile()`, never reachable over REST before. */
export interface DuplicateScreeningProfileRequest {
  new_name: string;
}

export interface ListScreeningProfilesParams {
  page?: number;
  page_size?: number;
  sort?: string;
  /** Frontend Milestone 4 addition — case-insensitive substring match. */
  name?: string;
  [key: string]: string | number | undefined;
}

/** Normalized company metrics — mirrors `app.screening.models.CompanyMetrics`
 * field-for-field. `extra="forbid"` on the backend model means this must
 * stay a closed set (no index signature): every screenable field name
 * comes from here, never invented or passed through client-side. Only
 * `ticker`/`company_name` are required. */
export interface CompanyMetrics {
  ticker: string;
  company_name: string;

  country?: string | null;
  sector?: string | null;
  industry?: string | null;

  market_cap?: number | null;
  price?: number | null;
  pe_ratio?: number | null;
  forward_pe?: number | null;
  pb_ratio?: number | null;
  ps_ratio?: number | null;
  ev_ebitda?: number | null;

  revenue_growth?: number | null;
  earnings_growth?: number | null;
  eps_growth?: number | null;

  gross_margin?: number | null;
  operating_margin?: number | null;
  net_margin?: number | null;

  roe?: number | null;
  roa?: number | null;
  roic?: number | null;

  debt_to_equity?: number | null;
  current_ratio?: number | null;
  quick_ratio?: number | null;

  free_cash_flow?: number | null;
  fcf_margin?: number | null;

  dividend_yield?: number | null;
  payout_ratio?: number | null;

  beta?: number | null;
  volatility?: number | null;

  analyst_rating?: string | null;
  analyst_target_upside?: number | null;

  insider_ownership?: number | null;
  institutional_ownership?: number | null;
}

export interface RunScreeningRequest {
  profile_id: string;
  companies: CompanyMetrics[];
}

/** `reason` is only ever set on failure — a passed filter has `reason: null`. */
export interface FilterEvaluation {
  filter_id: string;
  field: string;
  operator: ScreenOperator;
  passed: boolean;
  reason: string | null;
}

export interface ScreenResultDetails {
  total_filters: number;
  enabled_filters: number;
  disabled_filters: number;
  [key: string]: unknown;
}

export interface ScreenResult {
  ticker: string;
  company_name: string | null;
  passed: boolean;
  matched_filters: FilterEvaluation[];
  failed_filters: FilterEvaluation[];
  score: number;
  details: ScreenResultDetails;
}

/** `result_id` is the HTTP-layer cache key — key every UI reference
 * (routing, comparison, session-recent list) off this. */
export interface ScreeningRunEnvelope {
  result_id: string;
  profile_id: string;
  results: ScreenResult[];
}
