import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Badge } from "@/components/badge";
import { EmptyState } from "@/components/states/empty-state";
import { useSessionActivityStore } from "@/store/session-activity-store";

/** Reads this browser session's own screening-run activity only — see
 * `session-activity-store.ts`'s module docstring for why there is no
 * durable, cross-session history to show instead. */
export function RecentScreeningRunsList(): ReactNode {
  const recentRuns = useSessionActivityStore((state) => state.recentScreeningRuns);

  if (recentRuns.length === 0) {
    return <EmptyState icon="🕓" title="No screens run yet this session" description="Run a screen against a profile to see it here." />;
  }

  return (
    <ul className="flex flex-col gap-2">
      {recentRuns.map((entry) => (
        <li
          key={entry.resultId}
          className="flex items-center justify-between gap-3 rounded-md border border-slate-200 px-3 py-2 dark:border-slate-800"
        >
          <div className="min-w-0">
            <Link
              to="/screening/results/$resultId"
              params={{ resultId: entry.resultId }}
              className="font-medium text-brand-700 hover:underline dark:text-brand-400"
            >
              {entry.profileName}
            </Link>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {entry.companyCount} {entry.companyCount === 1 ? "company" : "companies"} · {new Date(entry.ranAt).toLocaleString()}
            </p>
          </div>
          <Badge label={`${String(entry.matchedCount)} matched`} tone="neutral" />
        </li>
      ))}
    </ul>
  );
}
