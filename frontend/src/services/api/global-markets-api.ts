import { apiClient } from "@/services/api/client";
import { ApiError } from "@/services/api/errors";
import { buildQueryString } from "@/lib/query-string";
import type { PaginatedResponse, SuccessResponse } from "@/types/api";
import type {
  CategoryIntelligenceReport,
  IntelligenceRun,
  RankedAsset,
  ReportCategory,
  ReportCategoryDefinition,
} from "@/types/global-markets";

/** Every Top-15/Top-20 ranked-asset list is small and fixed-size (see
 * `REPORT_CATEGORY_DEFINITIONS`'s own `top_n`) — one page at the API's
 * own maximum page size always returns every asset in a category, so
 * this frontend never needs to paginate through more than one page. */
const RANKED_ASSETS_PAGE_SIZE = 100;

/** How many past runs the run picker (see `RunPicker`) offers — a
 * bounded recent window, not a full paginated browse-everything UI. */
const RUN_HISTORY_PAGE_SIZE = 30;

/** Thin wrappers over the read-only `/api/v1/global-markets/*` REST
 * surface (`app/api/v1/global_markets/router.py`) — no logic beyond the
 * HTTP call and unwrapping `.data`. There is no POST/trigger endpoint by
 * design: every entity here is produced by the scheduled
 * `GlobalMarketIntelligenceWorkflow`, never by an API request. */
export const globalMarketsApi = {
  listCategories: async (): Promise<ReportCategoryDefinition[]> => {
    const response = await apiClient.get<SuccessResponse<ReportCategoryDefinition[]>>("/global-markets/categories");
    return response.data;
  },

  getLatestRun: async (): Promise<IntelligenceRun> => {
    const response = await apiClient.get<SuccessResponse<IntelligenceRun>>("/global-markets/runs/latest");
    return response.data;
  },

  /** Most-recent-first, for the historical run picker (`RunPicker`) —
   * a bounded recent window (`RUN_HISTORY_PAGE_SIZE`), not a full
   * paginated browse-everything UI. */
  listRuns: async (): Promise<PaginatedResponse<IntelligenceRun>> => {
    return apiClient.get<PaginatedResponse<IntelligenceRun>>(
      `/global-markets/runs${buildQueryString({ sort: "run_date", direction: "desc", page_size: RUN_HISTORY_PAGE_SIZE })}`,
    );
  },

  getRun: async (runId: string): Promise<IntelligenceRun> => {
    const response = await apiClient.get<SuccessResponse<IntelligenceRun>>(`/global-markets/runs/${runId}`);
    return response.data;
  },

  listRankedAssets: async (runId: string, category: ReportCategory): Promise<PaginatedResponse<RankedAsset>> => {
    return apiClient.get<PaginatedResponse<RankedAsset>>(
      `/global-markets/runs/${runId}/categories/${category}/ranked-assets${buildQueryString({ page_size: RANKED_ASSETS_PAGE_SIZE })}`,
    );
  },

  /** `null` when no narrative report was generated for this category —
   * mirrors the API's own 404 (`get_report_for_category`), not treated
   * as an error: a report is a supplementary narrative, the ranked list
   * itself is the primary content. */
  getCategoryReport: async (runId: string, category: ReportCategory): Promise<CategoryIntelligenceReport | null> => {
    try {
      const response = await apiClient.get<SuccessResponse<CategoryIntelligenceReport>>(
        `/global-markets/runs/${runId}/categories/${category}/report`,
      );
      return response.data;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },
};
