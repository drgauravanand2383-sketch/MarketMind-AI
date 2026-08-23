import { apiClient } from "@/services/api/client";
import { buildQueryString } from "@/lib/query-string";
import type { PaginatedResponse, SuccessResponse } from "@/types/api";
import type { Watchlist, WatchlistListParams, WatchlistStatistics } from "@/types/watchlist";
import type {
  GenerateRecommendationsRequest,
  InitialAnalysisState,
  PortfolioIntelligenceReport,
  RecommendationResult,
  RiskAssessment,
} from "@/types/portfolio";

/** Thin wrappers over `/api/v1/portfolio/*`. There is no separate
 * `Portfolio` domain model — a `portfolio_id` *is* a `watchlist_id`, so
 * `list`/`get` return the exact `Watchlist` shape. `summary`/
 * `intelligence`/`risk`/`recommendations` take `portfolio_id` as a
 * query param (not a path segment) on the real backend routes. Nothing
 * here computes anything — every value is exactly what the backend
 * returned (M3 spec: "Do not compute anything on the frontend"). */
export const portfolioApi = {
  list: async (params: WatchlistListParams = {}): Promise<PaginatedResponse<Watchlist>> => {
    return apiClient.get<PaginatedResponse<Watchlist>>(`/portfolio${buildQueryString(params)}`);
  },

  get: async (portfolioId: string): Promise<Watchlist> => {
    const response = await apiClient.get<SuccessResponse<Watchlist>>(`/portfolio/${portfolioId}`);
    return response.data;
  },

  getSummary: async (portfolioId: string): Promise<WatchlistStatistics> => {
    const response = await apiClient.get<SuccessResponse<WatchlistStatistics>>(
      `/portfolio/summary${buildQueryString({ portfolio_id: portfolioId })}`,
    );
    return response.data;
  },

  /** `503` if the backend has no `ANTHROPIC_API_KEY` configured — a
   * `service_unavailable` `ApiError`, not something callers should
   * treat as "no report exists yet" the way `getRisk`/`getRecommendations`
   * do. `skipRetry: true` because that 503 means "not configured on this
   * deployment," a stable fact for the deployment's lifetime, not a
   * transient blip — `ApiClient`'s default policy would otherwise retry
   * a 503 twice with backoff before ever surfacing it. */
  getIntelligence: async (portfolioId: string): Promise<PortfolioIntelligenceReport> => {
    const response = await apiClient.get<SuccessResponse<PortfolioIntelligenceReport>>(
      `/portfolio/intelligence${buildQueryString({ portfolio_id: portfolioId })}`,
      { skipRetry: true },
    );
    return response.data;
  },

  /** Throws `ApiError` with `status === 404` if no risk assessment has
   * been generated for this portfolio yet — that 404 *is* the
   * "unavailable" signal; there is no separate boolean flag. */
  getRisk: async (portfolioId: string): Promise<RiskAssessment> => {
    const response = await apiClient.get<SuccessResponse<RiskAssessment>>(
      `/portfolio/risk${buildQueryString({ portfolio_id: portfolioId })}`,
    );
    return response.data;
  },

  /** Same 404-means-unavailable convention as `getRisk`. */
  getRecommendations: async (portfolioId: string): Promise<RecommendationResult> => {
    const response = await apiClient.get<SuccessResponse<RecommendationResult>>(
      `/portfolio/recommendations${buildQueryString({ portfolio_id: portfolioId })}`,
    );
    return response.data;
  },

  /** Not called anywhere in this milestone's UI — kept for API-module
   * completeness/symmetry only (see `GenerateRecommendationsRequest`'s
   * own docstring). */
  generateRecommendations: async (body: GenerateRecommendationsRequest): Promise<RecommendationResult> => {
    const response = await apiClient.post<SuccessResponse<RecommendationResult>>("/portfolio/recommendations", body);
    return response.data;
  },

  /** v1.2 Priority 8. Never 404s for "not yet analyzed" the way `getRisk`/
   * `getRecommendations` do — a portfolio that exists always has a status
   * (ANALYZING/READY/PARTIAL/UNAVAILABLE/ERROR); only a nonexistent
   * `portfolioId` 404s. */
  getAnalysisStatus: async (portfolioId: string): Promise<InitialAnalysisState> => {
    const response = await apiClient.get<SuccessResponse<InitialAnalysisState>>(
      `/portfolio/${portfolioId}/analysis-status`,
    );
    return response.data;
  },

  /** v1.2 Priority 8. Dispatches (or retries) the initial analysis job and
   * returns immediately with the status as of *before* that job runs — a
   * safe no-op if analysis already exists or is already in flight. */
  triggerAnalysis: async (portfolioId: string): Promise<InitialAnalysisState> => {
    const response = await apiClient.post<SuccessResponse<InitialAnalysisState>>(
      `/portfolio/${portfolioId}/analysis`,
    );
    return response.data;
  },
};
