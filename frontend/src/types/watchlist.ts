/**
 * Mirrors `app.watchlist.models` and `app.api.v1.watchlists.schemas`
 * field-for-field (verified against the actual backend source, Frontend
 * Milestone 3 — see `docs/release/API_CONTRACT_V1.md`). `sector`/
 * `country`/`theme` are free strings on the backend, not closed enums —
 * do not model them as string-literal unions.
 */

export interface WatchlistItem {
  ticker: string;
  company_name: string | null;
  country: string | null;
  sector: string | null;
  theme: string | null;
  source_agent: string | null;
  confidence: number | null;
  reason: string | null;
  added_at: string;
  notes: string | null;
}

export interface Watchlist {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  items: WatchlistItem[];
}

export interface WatchlistSnapshot {
  watchlist_id: string;
  snapshot_time: string;
  total_companies: number;
  average_confidence: number | null;
  summary: string;
}

/** Response of `GET /portfolio/summary` too — `portfolio_id` *is* a
 * `watchlist_id`; there is no separate `Portfolio` domain model. */
export interface WatchlistStatistics {
  watchlist_id: string;
  total_companies: number;
  average_confidence: number | null;
  top_sectors: string[];
  sector_distribution: Record<string, number>;
  country_distribution: Record<string, number>;
  theme_distribution: Record<string, number>;
}

export interface CreateWatchlistRequest {
  name: string;
  description?: string;
}

export interface RenameWatchlistRequest {
  name: string;
}

export interface AddCompanyRequest {
  ticker: string;
  company_name?: string | null;
  country?: string | null;
  sector?: string | null;
  theme?: string | null;
  source_agent?: string | null;
  confidence?: number | null;
  reason?: string | null;
  notes?: string | null;
}

/** `PATCH /watchlists/{id}/companies/{ticker}/notes` — Frontend
 * Milestone 3's backend addition; see `docs/release/API_CONTRACT_V1.md` §1. */
export interface UpdateNotesRequest {
  notes: string;
}

export type SortDirection = "asc" | "desc";

/** The *only* three values the backend's `sort` query param accepts for
 * both `/watchlists` and `/portfolio` — a fourth value is a `422`. */
export type WatchlistSortField = "name" | "created_at" | "updated_at";

export interface WatchlistListParams {
  /** Lets `WatchlistListParams` be passed directly to `buildQueryString`
   * (`@/lib/query-string`) without a cast — every named field below is
   * already within this value type, so the index signature only widens
   * what TS considers the object assignable to, changing nothing about
   * how callers construct or read it. */
  [key: string]: string | number | undefined;
  page?: number;
  page_size?: number;
  sort?: WatchlistSortField;
  direction?: SortDirection;
  /** Case-insensitive substring match on the watchlist's own `name` —
   * the frontend's search box; a Frontend Milestone 3 backend addition
   * (see `docs/release/API_CONTRACT_V1.md` §1). */
  name?: string;
  sector?: string;
  country?: string;
  theme?: string;
  ticker?: string;
  company?: string;
  created_after?: string;
  created_before?: string;
}
