import type { ReactNode } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import { useResearchReport } from "@/hooks/use-research";
import { useScreeningProfile, useScreeningResult } from "@/hooks/use-screening";
import { useWatchlist } from "@/hooks/use-watchlists";
import { FEATURE_NAV_ITEMS } from "@/lib/nav-items";
import { useDecisionHistoryStore, type DecisionHistoryEntry } from "@/store/decision-history-store";

function isBacktestRunEntry(entry: DecisionHistoryEntry): entry is Extract<DecisionHistoryEntry, { kind: "backtest_run" }> {
  return entry.kind === "backtest_run";
}

function labelForSegment(segment: string): string {
  const item = FEATURE_NAV_ITEMS.find((entry) => entry.to === `/${segment}`);
  if (item) return item.label;
  return segment.charAt(0).toUpperCase() + segment.slice(1);
}

/** `/watchlists/$watchlistId`'s last segment is a raw UUID —
 * title-casing it would show gibberish instead of the watchlist's own
 * name. Resolved via the same query the detail page itself uses, so
 * this is normally a cache hit, not an extra request. Always called
 * (Rules of Hooks), with the query itself disabled unless the path
 * actually matches. */
function useWatchlistDetailCrumbLabel(segments: string[]): string | null {
  const isWatchlistDetail = segments[0] === "watchlists" && segments.length === 2;
  const watchlistId = isWatchlistDetail ? (segments[1] ?? "") : "";
  const watchlist = useWatchlist(watchlistId);
  return isWatchlistDetail ? (watchlist.data?.name ?? null) : null;
}

/** `/research/$requestId`'s last segment is a raw id — resolved to the
 * company name via the same query the result page itself uses (normally
 * a cache hit). "batch" and "compare" are literal, non-id segments and
 * must not be sent through this lookup. */
function useResearchDetailCrumbLabel(segments: string[]): string | null {
  const isResearchDetail =
    segments[0] === "research" && segments.length === 2 && segments[1] !== "batch" && segments[1] !== "compare";
  const requestId = isResearchDetail ? (segments[1] ?? "") : "";
  const report = useResearchReport(requestId);
  return isResearchDetail ? (report.data?.report.company_overview.company_name ?? null) : null;
}

/** `/screening/$profileId`'s last segment is a raw id — resolved to the
 * profile name via the same query the detail page itself uses. "results"
 * is a literal, non-id segment and must not be sent through this lookup. */
function useScreeningProfileCrumbLabel(segments: string[]): string | null {
  const isProfileDetail = segments[0] === "screening" && segments.length === 2 && segments[1] !== "results";
  const profileId = isProfileDetail ? (segments[1] ?? "") : "";
  const profile = useScreeningProfile(profileId);
  return isProfileDetail ? (profile.data?.name ?? null) : null;
}

/** `/screening/results/$resultId` resolves to the run's own profile name
 * (a cache hit against the same query the results page itself uses),
 * one level removed via `profile_id` on the cached run envelope. */
function useScreeningResultCrumbLabel(segments: string[]): string | null {
  const isResultDetail = segments[0] === "screening" && segments[1] === "results" && segments.length === 3;
  const resultId = isResultDetail ? (segments[2] ?? "") : "";
  const result = useScreeningResult(resultId);
  const profile = useScreeningProfile(result.data?.profile_id ?? "");
  return isResultDetail ? (profile.data ? `${profile.data.name} result` : null) : null;
}

/** `/decisions/$portfolioId`'s last segment is a raw watchlist id
 * (`portfolio_id` *is* a `watchlist_id`) — resolved to the watchlist's
 * own name via the same query the workspace page itself uses. */
function useDecisionWorkspaceCrumbLabel(segments: string[]): string | null {
  const isWorkspace = segments[0] === "decisions" && segments.length === 2;
  const portfolioId = isWorkspace ? (segments[1] ?? "") : "";
  const watchlist = useWatchlist(portfolioId);
  return isWorkspace ? (watchlist.data?.name ?? null) : null;
}

/** `/historical-analysis/backtests/$runId`'s last segment is a raw id —
 * neither `BacktestRun` nor `BacktestResult` carries a human-readable
 * `name` (only the original `BacktestRequest` did, and it's never
 * returned by any GET endpoint), so this falls back to this session's
 * own history (which does remember the name it was created with) rather
 * than showing a raw UUID; a run loaded from a previous session shows a
 * generic label instead. "compare" is a literal, non-id segment. */
function useBacktestDetailCrumbLabel(segments: string[]): string | null {
  const isBacktestDetail = segments[0] === "historical-analysis" && segments[1] === "backtests" && segments.length === 3 && segments[2] !== "compare";
  const runId = isBacktestDetail ? (segments[2] ?? "") : "";
  const historyName = useDecisionHistoryStore((state) => {
    const entry = state.entries.filter(isBacktestRunEntry).find((candidate) => candidate.runId === runId);
    return entry?.name;
  });
  if (!isBacktestDetail) return null;
  return historyName ?? "Backtest";
}

/** `/historical-analysis/explainability/$requestId`'s last segment is a
 * raw id — `ExplainabilityResult` carries no human-readable name either.
 * "compare" is a literal, non-id segment. */
function useExplainabilityDetailCrumbLabel(segments: string[]): string | null {
  const isExplainabilityDetail =
    segments[0] === "historical-analysis" && segments[1] === "explainability" && segments.length === 3 && segments[2] !== "compare";
  return isExplainabilityDetail ? "Explanation" : null;
}

/** Derives the trail purely from the current pathname — every route
 * segment maps to a label via `FEATURE_NAV_ITEMS` (falling back to a
 * title-cased segment), so a new domain route needs no separate
 * breadcrumb configuration of its own. */
export function Breadcrumbs(): ReactNode {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const segments = pathname.split("/").filter(Boolean);
  const watchlistDetailLabel = useWatchlistDetailCrumbLabel(segments);
  const researchDetailLabel = useResearchDetailCrumbLabel(segments);
  const screeningProfileLabel = useScreeningProfileCrumbLabel(segments);
  const screeningResultLabel = useScreeningResultCrumbLabel(segments);
  const decisionWorkspaceLabel = useDecisionWorkspaceCrumbLabel(segments);
  const backtestDetailLabel = useBacktestDetailCrumbLabel(segments);
  const explainabilityDetailLabel = useExplainabilityDetailCrumbLabel(segments);
  const detailLabel =
    watchlistDetailLabel ??
    researchDetailLabel ??
    screeningProfileLabel ??
    screeningResultLabel ??
    decisionWorkspaceLabel ??
    backtestDetailLabel ??
    explainabilityDetailLabel;

  if (segments.length === 0) {
    return null;
  }

  const crumbs = segments.map((segment, index) => ({
    to: `/${segments.slice(0, index + 1).join("/")}`,
    label: index === segments.length - 1 && detailLabel ? detailLabel : labelForSegment(segment),
  }));

  return (
    <nav aria-label="Breadcrumb" className="px-6 pt-4">
      <ol className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
        <li>
          <Link to="/" className="hover:text-slate-700 dark:hover:text-slate-200">
            Dashboard
          </Link>
        </li>
        {crumbs.map((crumb, index) => {
          const isLast = index === crumbs.length - 1;
          return (
            <li key={crumb.to} className="flex items-center gap-1.5">
              <span aria-hidden="true">/</span>
              {isLast ? (
                <span aria-current="page" className="font-medium text-slate-900 dark:text-slate-100">
                  {crumb.label}
                </span>
              ) : (
                <Link to={crumb.to} className="hover:text-slate-700 dark:hover:text-slate-200">
                  {crumb.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
