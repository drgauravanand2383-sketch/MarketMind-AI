import type { ReactNode } from "react";
import { useRuns } from "@/hooks/use-global-markets";
import { useGlobalMarketsStore } from "@/store/global-markets-store";

/**
 * Lets the user pick a past run instead of always the latest one.
 * `useRuns()` fetches a bounded recent window (see `globalMarketsApi
 * .listRuns`'s own `RUN_HISTORY_PAGE_SIZE`), sorted most-recent-first.
 * Renders nothing while that list is still loading/empty/erroring — the
 * page already shows the latest run regardless, so a slow/failed history
 * fetch is never itself a blocking error.
 */
export function RunPicker(): ReactNode {
  const runs = useRuns();
  const selectedRunId = useGlobalMarketsStore((state) => state.selectedRunId);
  const setSelectedRunId = useGlobalMarketsStore((state) => state.setSelectedRunId);

  if (!runs.data || runs.data.data.length === 0) return null;

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="global-markets-run-picker" className="text-sm text-slate-500 dark:text-slate-400">
        Run
      </label>
      <select
        id="global-markets-run-picker"
        value={selectedRunId ?? ""}
        onChange={(event) => {
          setSelectedRunId(event.target.value === "" ? null : event.target.value);
        }}
        className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      >
        <option value="">Latest</option>
        {runs.data.data.map((run) => (
          <option key={run.id} value={run.id}>
            {run.run_date} — {run.status}
          </option>
        ))}
      </select>
    </div>
  );
}
