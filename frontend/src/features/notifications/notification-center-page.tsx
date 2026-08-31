import { useMemo, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { PriorityBadge, type PriorityLevel } from "@/components/priority-badge";
import { EmptyState } from "@/components/states/empty-state";
import {
  decisionDomainLabel,
  useRealtimeNotificationStore,
  type NotificationCenterEntry,
  type NotificationDomain,
} from "@/store/realtime-notification-store";
import { ALL_NOTIFICATION_DOMAINS, useNotificationFilterStore, type NotificationReadFilter } from "@/store/notification-filter-store";

const DOMAIN_LABELS: Record<NotificationDomain, string> = {
  alerts: "Alerts",
  backtests: "Backtests",
  recommendations: "Recommendations",
  strategy: "Strategy",
  explainability: "Explainability",
  health: "Health",
  market: "Market",
  news: "News",
  decisions: "Decisions",
  global_markets: "Global Markets",
};

const PRIORITY_OPTIONS: (PriorityLevel | "")[] = ["", "LOW", "MODERATE", "MEDIUM", "HIGH", "CRITICAL"];

function dateGroupLabel(occurredAt: string): string {
  const date = new Date(occurredAt);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return "Today";
  if (date.toDateString() === yesterday.toDateString()) return "Yesterday";
  return date.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
}

function groupByDate(entries: NotificationCenterEntry[]): { label: string; entries: NotificationCenterEntry[] }[] {
  const groups: { label: string; entries: NotificationCenterEntry[] }[] = [];
  for (const entry of entries) {
    const label = dateGroupLabel(entry.occurredAt);
    const existing = groups.find((group) => group.label === label);
    if (existing) {
      existing.entries.push(entry);
    } else {
      groups.push({ label, entries: [entry] });
    }
  }
  return groups;
}

function entryLink(entry: NotificationCenterEntry): { to: string; params: Record<string, string> } | null {
  switch (entry.entityRef.kind) {
    case "backtest":
      return { to: "/historical-analysis/backtests/$runId", params: { runId: entry.entityRef.runId } };
    case "explainability":
      return { to: "/historical-analysis/explainability/$requestId", params: { requestId: entry.entityRef.requestId } };
    case "global_markets":
      // No run-specific route exists — the landing page always shows the
      // latest run, which is exactly what this entry is about.
      return { to: "/global-markets", params: {} };
    case "market":
    case "news":
    case "decision":
      // Milestone 15: only deep-linkable when Decision Impact attached a
      // portfolio_id — a portfolio-agnostic change (no watchlist tracks
      // that entity yet) has nowhere to link to.
      return entry.entityRef.portfolioId
        ? { to: "/decisions/$portfolioId", params: { portfolioId: entry.entityRef.portfolioId } }
        : null;
    default:
      return null;
  }
}

function NotificationRow({ entry }: { entry: NotificationCenterEntry }): ReactNode {
  const markRead = useRealtimeNotificationStore((state) => state.markRead);
  const link = entryLink(entry);

  const content = (
    <>
      <div className="flex items-center gap-2">
        {!entry.read && <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full bg-brand-600" />}
        <span className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{DOMAIN_LABELS[entry.domain]}</span>
        {entry.priority && <PriorityBadge level={entry.priority} />}
      </div>
      <p className={`mt-1 text-sm ${entry.read ? "text-slate-600 dark:text-slate-400" : "font-medium text-slate-900 dark:text-slate-100"}`}>{entry.title}</p>
      {/* v1.2 Priority 3: a digest of 2+ decision changes shows each one
       * on its own line (§6's own "Details:" example) instead of the
       * single joined-sentence summary every other entry (and a
       * digest of exactly 1) already uses unchanged. */}
      {entry.digest !== undefined && entry.digest.changes.length > 1 ? (
        <ul className="mt-0.5 list-disc space-y-0.5 pl-4 text-xs text-slate-500 dark:text-slate-400">
          {entry.digest.changes.map((change) => (
            <li key={change.eventFingerprint}>
              {decisionDomainLabel(change.domain)}:{" "}
              {change.previousValue !== null && change.currentValue !== null ? `${change.previousValue} → ${change.currentValue}` : change.summary}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{entry.summary}</p>
      )}
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{new Date(entry.occurredAt).toLocaleString()}</p>
    </>
  );

  const className = "block w-full rounded-md border border-slate-200 p-3 text-left hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/60";

  if (link) {
    return (
      <li>
        <Link
          to={link.to}
          params={link.params}
          onClick={() => {
            markRead(entry.id);
          }}
          className={className}
        >
          {content}
        </Link>
      </li>
    );
  }

  return (
    <li>
      <button
        type="button"
        onClick={() => {
          markRead(entry.id);
        }}
        className={className}
      >
        {content}
      </button>
    </li>
  );
}

/**
 * The Notification Center's full history page — session-only (see
 * `realtime-notification-store.ts`'s module docstring for why there is
 * no durable, cross-session history to show instead). All filtering here
 * is client-side over the in-memory `entries` array — there is no
 * backend endpoint for this session-only data to filter/search
 * server-side, the same reasoned exception every other session-only
 * list in this app (M4-M6) already established.
 */
export function NotificationCenterPage(): ReactNode {
  const allEntries = useRealtimeNotificationStore((state) => state.entries);
  const markAllRead = useRealtimeNotificationStore((state) => state.markAllRead);
  const clear = useRealtimeNotificationStore((state) => state.clear);

  const domainFilter = useNotificationFilterStore((state) => state.domains);
  const readFilter = useNotificationFilterStore((state) => state.readFilter);
  const priorityFilter = useNotificationFilterStore((state) => state.priority);
  const search = useNotificationFilterStore((state) => state.search);
  const toggleDomain = useNotificationFilterStore((state) => state.toggleDomain);
  const setReadFilter = useNotificationFilterStore((state) => state.setReadFilter);
  const setPriorityFilter = useNotificationFilterStore((state) => state.setPriority);
  const setSearch = useNotificationFilterStore((state) => state.setSearch);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return allEntries.filter((entry) => {
      if (!domainFilter.includes(entry.domain)) return false;
      if (readFilter === "unread" && entry.read) return false;
      if (readFilter === "read" && !entry.read) return false;
      if (priorityFilter && entry.priority !== priorityFilter) return false;
      if (needle && !entry.title.toLowerCase().includes(needle) && !entry.summary.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [allEntries, domainFilter, readFilter, priorityFilter, search]);

  const groups = useMemo(() => groupByDate(filtered), [filtered]);

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Notification Center</h1>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Real-time alerts, recommendations, backtests, strategy evaluations, explainability reports, and health changes —
            this browser session only.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={markAllRead}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Mark all read
          </button>
          <button
            type="button"
            onClick={clear}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Clear
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div role="group" aria-label="Filter by domain" className="flex flex-wrap gap-2">
          {ALL_NOTIFICATION_DOMAINS.map((domain) => (
            <label key={domain} className="flex items-center gap-1.5 text-sm text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={domainFilter.includes(domain)}
                onChange={() => {
                  toggleDomain(domain);
                }}
              />
              {DOMAIN_LABELS[domain]}
            </label>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="notification-search">
            Search notifications
          </label>
          <input
            id="notification-search"
            type="search"
            data-shortcut-target="search"
            placeholder="Search title or summary…"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
            }}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />

          <label className="sr-only" htmlFor="notification-read-filter">
            Filter by read status
          </label>
          <select
            id="notification-read-filter"
            value={readFilter}
            onChange={(event) => {
              setReadFilter(event.target.value as NotificationReadFilter);
            }}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            <option value="all">All</option>
            <option value="unread">Unread</option>
            <option value="read">Read</option>
          </select>

          <label className="sr-only" htmlFor="notification-priority-filter">
            Filter by priority
          </label>
          <select
            id="notification-priority-filter"
            value={priorityFilter}
            onChange={(event) => {
              setPriorityFilter(event.target.value as PriorityLevel | "");
            }}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            {PRIORITY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option || "All priorities"}
              </option>
            ))}
          </select>
        </div>
      </div>

      {allEntries.length === 0 ? (
        <EmptyState icon="🔔" title="No notifications yet this session" description="Real-time events will appear here as they arrive." />
      ) : filtered.length === 0 ? (
        <EmptyState title="No notifications match your filters" description="Try clearing a filter or the search box." />
      ) : (
        <div className="flex flex-col gap-4">
          {groups.map((group) => (
            <div key={group.label}>
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{group.label}</h2>
              <ul className="flex flex-col gap-2">
                {group.entries.map((entry) => (
                  <NotificationRow key={entry.id} entry={entry} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
