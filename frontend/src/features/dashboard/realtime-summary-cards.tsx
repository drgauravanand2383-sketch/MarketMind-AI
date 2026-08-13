import type { ReactNode } from "react";
import { useRealtimeNotificationStore } from "@/store/realtime-notification-store";

/**
 * Two session-scoped WebSocket-event tallies, not real backend
 * aggregates — there is no "total recommendations" endpoint at all
 * (recommendations are generate-on-demand, never listed), so the alert
 * count is treated the same way for consistency rather than mixing a
 * real `GET /alerts` total with a session tally on the same dashboard
 * (approved product decision, `docs/frontend/MILESTONE_7.md`). Both
 * counts are a plain `.filter().length` over `realtime-notification
 * -store`'s already-collected `entries` — no second counter to keep in
 * sync.
 */
export function RealtimeSummaryCards(): ReactNode {
  const entries = useRealtimeNotificationStore((state) => state.entries);
  const recommendationCount = entries.filter((entry) => entry.domain === "recommendations").length;
  const alertCount = entries.filter((entry) => entry.domain === "alerts").length;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2" aria-live="polite">
      <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
        <p className="text-xs text-slate-500 dark:text-slate-400">Recommendations generated this session</p>
        <p className="mt-1 text-xl font-semibold text-slate-900 dark:text-slate-100">{recommendationCount}</p>
      </div>
      <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
        <p className="text-xs text-slate-500 dark:text-slate-400">Alerts generated this session</p>
        <p className="mt-1 text-xl font-semibold text-slate-900 dark:text-slate-100">{alertCount}</p>
      </div>
    </div>
  );
}
