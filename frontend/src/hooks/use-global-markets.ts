import { useQueries, useQuery } from "@tanstack/react-query";
import { globalMarketsApi } from "@/services/api/global-markets-api";
import {
  MAIN_REPORT_CATEGORIES,
  PENNY_MICROCAP_REPORT_CATEGORIES,
  type RankedAsset,
  type ReportCategory,
} from "@/types/global-markets";

/** All nine report categories, main first — the fixed set the "Top
 * Picks" view and the dashboard preview aggregate across. */
export const ALL_REPORT_CATEGORIES: ReportCategory[] = [...MAIN_REPORT_CATEGORIES, ...PENNY_MICROCAP_REPORT_CATEGORIES];

export const globalMarketsKeys = {
  all: ["global-markets"] as const,
  categories: () => [...globalMarketsKeys.all, "categories"] as const,
  runs: () => [...globalMarketsKeys.all, "runs"] as const,
  latestRun: () => [...globalMarketsKeys.runs(), "latest"] as const,
  run: (runId: string) => [...globalMarketsKeys.runs(), runId] as const,
  rankedAssets: (runId: string, category: ReportCategory) => [...globalMarketsKeys.run(runId), "ranked-assets", category] as const,
  report: (runId: string, category: ReportCategory) => [...globalMarketsKeys.run(runId), "report", category] as const,
};

/** The nine fixed category definitions (display name, top_n, market
 * region/asset class) — effectively static, but fetched rather than
 * duplicated as a frontend constant, since `REPORT_CATEGORY_DEFINITIONS`
 * is backend-owned (`app/global_markets/models.py`) and this frontend
 * must never drift from it. */
export function useCategories() {
  return useQuery({
    queryKey: globalMarketsKeys.categories(),
    queryFn: () => globalMarketsApi.listCategories(),
    staleTime: Infinity,
  });
}

/** The one query every tab/panel starts from — which run's data to show.
 * `error.status === 404` means "no run has ever completed" (a real,
 * expected empty state — the scheduler hasn't produced a run yet), not a
 * failure; callers distinguish it from other errors themselves (same
 * pattern as `ScreeningResultsPage`'s own not-found handling). */
export function useLatestRun() {
  return useQuery({
    queryKey: globalMarketsKeys.latestRun(),
    queryFn: () => globalMarketsApi.getLatestRun(),
  });
}

/** The bounded recent-run history the `RunPicker` offers — see
 * `globalMarketsApi.listRuns`'s own `RUN_HISTORY_PAGE_SIZE` cap. */
export function useRuns() {
  return useQuery({
    queryKey: globalMarketsKeys.runs(),
    queryFn: () => globalMarketsApi.listRuns(),
  });
}

/** One specific historical run (not necessarily the latest) — used once
 * the `RunPicker` selects a past `run_date` instead of "Latest". */
export function useRun(runId: string) {
  return useQuery({
    queryKey: globalMarketsKeys.run(runId),
    queryFn: () => globalMarketsApi.getRun(runId),
    enabled: runId.length > 0,
  });
}

export function useRankedAssets(runId: string, category: ReportCategory) {
  return useQuery({
    queryKey: globalMarketsKeys.rankedAssets(runId, category),
    queryFn: () => globalMarketsApi.listRankedAssets(runId, category),
    enabled: runId.length > 0,
  });
}

export interface CategoryTopPicks {
  category: ReportCategory;
  /** This category's ranked assets, rank-ascending, truncated to the
   * requested preview depth. Never recomputed here — exactly the
   * persisted `RankedAsset` rows the API returned for this run. */
  assets: RankedAsset[];
  isPending: boolean;
  isError: boolean;
}

export interface TopPicksAcrossCategories {
  byCategory: CategoryTopPicks[];
  /** At least one category is still loading. */
  isPending: boolean;
  /** Every category's request failed — a genuine "couldn't load" state,
   * distinct from one category simply having no ranked assets. */
  isError: boolean;
  refetch: () => void;
}

/** The rank-1..`limit` ranked assets for **every** category of one run,
 * fanned out as one query per category (the all-categories endpoint is
 * capped below the 9x20 rows a full run can hold, and each per-category
 * query is independently cached — so opening a category tab afterwards is
 * instant). The frontend does no ranking or math: it only slices the
 * already-ranked, already-persisted list each category returned. */
export function useTopPicksAcrossCategories(runId: string, limit: number): TopPicksAcrossCategories {
  return useQueries({
    queries: ALL_REPORT_CATEGORIES.map((category) => ({
      queryKey: globalMarketsKeys.rankedAssets(runId, category),
      queryFn: () => globalMarketsApi.listRankedAssets(runId, category),
      enabled: runId.length > 0,
    })),
    combine: (results) => ({
      byCategory: ALL_REPORT_CATEGORIES.map((category, index) => {
        const result = results[index];
        return {
          category,
          assets: [...(result?.data?.data ?? [])].sort((a, b) => a.rank - b.rank).slice(0, limit),
          isPending: result?.isPending ?? true,
          isError: result?.isError ?? false,
        };
      }),
      isPending: results.some((result) => result.isPending),
      isError: results.length > 0 && results.every((result) => result.isError),
      refetch: () => {
        for (const result of results) void result.refetch();
      },
    }),
  });
}

export function useCategoryReport(runId: string, category: ReportCategory) {
  return useQuery({
    queryKey: globalMarketsKeys.report(runId, category),
    queryFn: () => globalMarketsApi.getCategoryReport(runId, category),
    enabled: runId.length > 0,
  });
}
