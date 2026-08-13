import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Badge } from "@/components/badge";
import { EmptyState } from "@/components/states/empty-state";
import { useSessionActivityStore } from "@/store/session-activity-store";

/** Reads this browser session's own research activity only — see
 * `session-activity-store.ts`'s module docstring for why there is no
 * durable, cross-session history to show instead. */
export function RecentResearchList(): ReactNode {
  const recentResearch = useSessionActivityStore((state) => state.recentResearch);

  if (recentResearch.length === 0) {
    return <EmptyState icon="🕓" title="No research run yet this session" description="Run a company research above to see it here." />;
  }

  return (
    <ul className="flex flex-col gap-2">
      {recentResearch.map((entry) => (
        <li
          key={entry.requestId}
          className="flex items-center justify-between gap-3 rounded-md border border-slate-200 px-3 py-2 dark:border-slate-800"
        >
          <div className="min-w-0">
            <Link
              to="/research/$requestId"
              params={{ requestId: entry.requestId }}
              className="font-medium text-brand-700 hover:underline dark:text-brand-400"
            >
              {entry.companyName}
            </Link>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {entry.ticker ?? "No ticker"} · {new Date(entry.ranAt).toLocaleString()}
            </p>
          </div>
          <Badge label={entry.matched ? "Matched" : "Unmatched"} tone={entry.matched ? "auto" : "neutral"} />
        </li>
      ))}
    </ul>
  );
}
