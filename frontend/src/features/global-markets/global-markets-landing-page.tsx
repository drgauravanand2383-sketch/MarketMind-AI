import type { ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { SkeletonList } from "@/components/states/skeleton";
import { CategoryPanel } from "@/features/global-markets/category-panel";
import { CATEGORY_DISPLAY_NAMES } from "@/features/global-markets/category-labels";
import { GlobalMarketsTabs } from "@/features/global-markets/global-markets-tabs";
import { PennyMicrocapSubTabs } from "@/features/global-markets/penny-microcap-subtabs";
import { useLatestRun } from "@/hooks/use-global-markets";
import { ApiError } from "@/services/api/errors";
import { useGlobalMarketsStore } from "@/store/global-markets-store";
import type { IntelligenceRunStatus } from "@/types/global-markets";

function statusTone(status: IntelligenceRunStatus): "success" | "warning" | "error" {
  if (status === "COMPLETED") return "success";
  if (status === "PARTIAL") return "warning";
  return "error";
}

const STATUS_BADGE_CLASS: Record<"success" | "warning" | "error", string> = {
  success: "bg-green-100 text-green-800 dark:bg-green-500/10 dark:text-green-400",
  warning: "bg-amber-100 text-amber-800 dark:bg-amber-500/10 dark:text-amber-400",
  error: "bg-red-100 text-red-800 dark:bg-red-500/10 dark:text-red-400",
};

/**
 * The Global Markets landing page — five main-category tabs (Top-15 each)
 * plus a "Penny & Micro-Cap" tab with 4 nested sub-tabs (Top-20 each),
 * all scoped to the most recent `IntelligenceRun`. There is no per-portfolio
 * concept here (unlike Decision Center) — one run's data is the same for
 * every user with `global_markets:read`, so this page needs no id param
 * and no portfolio picker, just the run-level data itself.
 */
export function GlobalMarketsLandingPage(): ReactNode {
  const latestRun = useLatestRun();
  const activeTab = useGlobalMarketsStore((state) => state.activeTab);
  const activePennySubTab = useGlobalMarketsStore((state) => state.activePennySubTab);

  if (latestRun.isPending) {
    return (
      <div className="p-6">
        <SkeletonList rows={6} rowClassName="h-10 w-full" />
      </div>
    );
  }

  if (latestRun.isError) {
    const isNoRunYet = latestRun.error instanceof ApiError && latestRun.error.status === 404;
    if (isNoRunYet) {
      return (
        <div className="p-6">
          <EmptyState
            icon="🌐"
            title="No intelligence run yet"
            description="The Global Market Intelligence scheduler hasn't completed a run yet. Check back after the next scheduled run."
          />
        </div>
      );
    }
    return (
      <div className="p-6">
        <ErrorState
          title="Couldn't load Global Markets"
          message={latestRun.error.message}
          onRetry={() => {
            void latestRun.refetch();
          }}
        />
      </div>
    );
  }

  const run = latestRun.data;
  const failedCategories = run.category_outcomes.filter((outcome) => !outcome.succeeded);
  const tone = statusTone(run.status);

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Global Markets</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Top-ranked opportunities across India, US, China, forex, and crypto.</p>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE_CLASS[tone]}`}>{run.status}</span>
          <span className="text-slate-500 dark:text-slate-400">Run date {run.run_date}</span>
        </div>
      </div>

      {failedCategories.length > 0 && (
        <div role="alert" className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
          {failedCategories.length} of {run.category_outcomes.length} categories failed to generate in this run:{" "}
          {failedCategories.map((outcome) => CATEGORY_DISPLAY_NAMES[outcome.category]).join(", ")}.
        </div>
      )}

      <GlobalMarketsTabs />

      <div role="tabpanel" id={`global-markets-tabpanel-${activeTab}`} aria-labelledby={`global-markets-tab-${activeTab}`} className="pt-4">
        {activeTab === "PENNY_MICROCAP" ? (
          <div className="flex flex-col gap-4">
            <PennyMicrocapSubTabs />
            <div
              role="tabpanel"
              id={`penny-microcap-subtabpanel-${activePennySubTab}`}
              aria-labelledby={`penny-microcap-subtab-${activePennySubTab}`}
            >
              <CategoryPanel runId={run.id} category={activePennySubTab} title={CATEGORY_DISPLAY_NAMES[activePennySubTab]} />
            </div>
          </div>
        ) : (
          <CategoryPanel runId={run.id} category={activeTab} title={CATEGORY_DISPLAY_NAMES[activeTab]} />
        )}
      </div>
    </div>
  );
}
