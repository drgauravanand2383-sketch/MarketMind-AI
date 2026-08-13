import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Badge } from "@/components/badge";
import { EmptyState } from "@/components/states/empty-state";
import { SkeletonList } from "@/components/states/skeleton";
import { useScreeningProfile, useScreeningResult } from "@/hooks/use-screening";
import { useComparisonStore } from "@/store/comparison-store";
import type { ScreeningRunEnvelope } from "@/types/screening";

interface Slot {
  resultId: string;
  envelope: ScreeningRunEnvelope | undefined;
  profileName: string | undefined;
  isPending: boolean;
  isError: boolean;
}

function useSlot(resultId: string): Slot {
  const result = useScreeningResult(resultId);
  const profile = useScreeningProfile(result.data?.profile_id ?? "");
  return {
    resultId,
    envelope: result.data,
    profileName: profile.data?.name,
    isPending: resultId.length > 0 && result.isPending,
    isError: result.isError,
  };
}

/** Compares up to 4 screening runs (capped by `useComparisonStore`) — a
 * per-ticker matrix of pass/fail across the selected runs, built purely
 * from already-fetched `ScreenResult`s. No score, filter, or metric is
 * recomputed; a row is only visually flagged when the runs' own
 * `passed` booleans disagree for that ticker. */
export function ScreeningComparePage(): ReactNode {
  const compareIds = useComparisonStore((state) => state.screeningResultIds);
  const clear = useComparisonStore((state) => state.clearScreeningResults);

  const slot0 = useSlot(compareIds[0] ?? "");
  const slot1 = useSlot(compareIds[1] ?? "");
  const slot2 = useSlot(compareIds[2] ?? "");
  const slot3 = useSlot(compareIds[3] ?? "");
  const slots = [slot0, slot1, slot2, slot3].slice(0, compareIds.length);

  if (compareIds.length < 2) {
    return (
      <div className="p-6">
        <EmptyState
          icon="⚖️"
          title="Select at least two screening runs to compare"
          description='Open a screening result and click "Add to comparison" — do this for two or more runs to see them here.'
        />
      </div>
    );
  }

  if (slots.some((slot) => slot.isPending)) {
    return (
      <div className="p-6">
        <SkeletonList rows={6} rowClassName="h-10 w-full" />
      </div>
    );
  }

  if (slots.some((slot) => slot.isError || !slot.envelope)) {
    return (
      <div className="p-6">
        <EmptyState
          icon="🧮"
          title="One or more runs are no longer available"
          description="Results aren't stored durably — run the screen again and re-select it for comparison."
        />
      </div>
    );
  }

  const tickers = [...new Set(slots.flatMap((slot) => slot.envelope?.results.map((r) => r.ticker) ?? []))].sort();

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Compare screening runs</h1>
        <button
          type="button"
          onClick={clear}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Clear selection
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Screening run comparison</caption>
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800">
              <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                Ticker
              </th>
              {slots.map((slot) => {
                const matched = slot.envelope?.results.filter((r) => r.passed).length ?? 0;
                const total = slot.envelope?.results.length ?? 0;
                return (
                  <th key={slot.resultId} scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                    <Link to="/screening/results/$resultId" params={{ resultId: slot.resultId }} className="hover:underline">
                      {slot.profileName ?? "Screen"}
                    </Link>
                    <p className="font-normal normal-case text-slate-500 dark:text-slate-400">
                      {matched}/{total} matched
                    </p>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {tickers.map((ticker) => {
              const statuses = slots.map((slot) => slot.envelope?.results.find((r) => r.ticker === ticker)?.passed);
              const defined = statuses.filter((status): status is boolean => status !== undefined);
              const differs = new Set(defined).size > 1;
              return (
                <tr
                  key={ticker}
                  className={`border-b border-slate-100 dark:border-slate-800/60 ${differs ? "bg-amber-50 dark:bg-amber-500/10" : ""}`}
                >
                  <td className="px-3 py-2 font-medium text-slate-800 dark:text-slate-200">{ticker}</td>
                  {statuses.map((status, index) => (
                    <td key={index} className="px-3 py-2">
                      {status === undefined ? (
                        <span className="text-slate-500 dark:text-slate-400">Not screened</span>
                      ) : (
                        <Badge label={status ? "Matched" : "Not matched"} tone={status ? "auto" : "neutral"} />
                      )}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
