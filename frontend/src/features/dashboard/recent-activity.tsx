import { useMemo, type ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";
import { useRealtimeNotificationStore, type NotificationCenterEntry } from "@/store/realtime-notification-store";
import { useSessionActivityStore, type RecentResearchEntry } from "@/store/session-activity-store";

interface ActivityItem {
  id: string;
  message: string;
  timestamp: string;
  type: "info" | "success" | "warning";
}

const MAX_DISPLAYED = 10;

const TYPE_DOT: Record<ActivityItem["type"], string> = {
  success: "bg-green-500",
  info: "bg-blue-500",
  warning: "bg-amber-500",
};

function activityTypeFor(entry: NotificationCenterEntry): ActivityItem["type"] {
  if (entry.priority === "CRITICAL" || entry.priority === "HIGH") return "warning";
  switch (entry.domain) {
    case "alerts":
      return "info";
    case "backtests":
      return entry.eventType === "BACKTEST_STARTED" ? "info" : "success";
    case "health":
      return entry.priority === "MODERATE" ? "warning" : "success";
    default:
      return "success";
  }
}

function fromNotification(entry: NotificationCenterEntry): ActivityItem {
  return { id: entry.id, message: entry.title, timestamp: entry.occurredAt, type: activityTypeFor(entry) };
}

function fromResearch(entry: RecentResearchEntry): ActivityItem {
  return {
    id: entry.requestId,
    message: `Research completed — ${entry.companyName}`,
    timestamp: entry.ranAt,
    type: "success",
  };
}

/**
 * A real, live activity feed — merges the 6 WebSocket-driven domain
 * events (`realtime-notification-store`) with this session's own
 * research completions (`session-activity-store`, Milestone 4). Research
 * has no WebSocket event at all (confirmed — the backend's `EventType`
 * enum has no research-related literal), so it can only ever come from
 * this session's own already-tracked activity, not a live event —
 * approved product decision, `docs/frontend/MILESTONE_7.md`. Both source
 * arrays are selected as stable references and merged/sorted/capped in
 * the component body (never inside a Zustand selector — see
 * `realtime-notification-store.ts`'s docstring on the M6 selector-loop
 * footgun this avoids).
 */
export function RecentActivity(): ReactNode {
  const notificationEntries = useRealtimeNotificationStore((state) => state.entries);
  const researchEntries = useSessionActivityStore((state) => state.recentResearch);

  const items = useMemo(
    () =>
      [...notificationEntries.map(fromNotification), ...researchEntries.map(fromResearch)]
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
        .slice(0, MAX_DISPLAYED),
    [notificationEntries, researchEntries],
  );

  if (items.length === 0) {
    return <EmptyState title="No recent activity" description="Real-time events and research runs from this session will appear here." />;
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-end">
        <span className="text-xs text-slate-500 dark:text-slate-400">This session</span>
      </div>
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <li key={item.id} className="flex items-start gap-3 rounded-md border border-slate-200 px-3 py-2 text-sm dark:border-slate-800">
            <span aria-hidden="true" className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${TYPE_DOT[item.type]}`} />
            <div>
              <p className="text-slate-800 dark:text-slate-200">{item.message}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">{new Date(item.timestamp).toLocaleString()}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
