import { useQuery } from "@tanstack/react-query";
import { globalMarketsApi } from "@/services/api/global-markets-api";
import type { ReportCategory } from "@/types/global-markets";

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

export function useCategoryReport(runId: string, category: ReportCategory) {
  return useQuery({
    queryKey: globalMarketsKeys.report(runId, category),
    queryFn: () => globalMarketsApi.getCategoryReport(runId, category),
    enabled: runId.length > 0,
  });
}
