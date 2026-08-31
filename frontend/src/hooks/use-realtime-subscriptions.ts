import { useAuthStore } from "@/store/auth-store";
import type { EventType } from "@/types/websocket";

/** Subscribing to an event type over `/ws` requires the same permission
 * its REST equivalent already requires (`app/api/ws/dependencies/
 * permissions.py`, `docs/architecture/WEBSOCKET_FRAMEWORK.md` §3) — a
 * client without it gets a non-fatal `{type:"error",code:"forbidden"}`.
 * `event_types: []` (server-side shorthand for "every type") is never
 * sent — it would require broad permission across every type at once,
 * which this frontend must not assume a given user has. */
const EVENT_TYPE_PERMISSIONS: Record<
  Exclude<
    EventType,
    "HEALTH_STATUS_CHANGED" | "RISK_ASSESSMENT_COMPLETED" | "MARKET_SNAPSHOT_REFRESHED" | "SIGNIFICANT_MARKET_CHANGE" | "SIGNIFICANT_NEWS_UPDATE"
  >,
  string
> = {
  ALERT_GENERATED: "alerts:read",
  BACKTEST_STARTED: "backtest:read",
  BACKTEST_COMPLETED: "backtest:read",
  RECOMMENDATION_GENERATED: "portfolio:read",
  STRATEGY_EVALUATION_COMPLETED: "strategy:read",
  EXPLAINABILITY_COMPLETED: "explainability:read",
  PORTFOLIO_INTELLIGENCE_UPDATED: "portfolio:read",
  PORTFOLIO_INTELLIGENCE_CHANGED: "portfolio:read",
  GLOBAL_MARKET_INTELLIGENCE_RUN_COMPLETED: "global_markets:read",
};

/** Needs authentication only, no specific permission — mirrors the
 * backend's own `_EVENT_TYPE_PERMISSIONS` unmapped entries exactly
 * (`app/api/ws/dependencies/permissions.py`): `HEALTH_STATUS_CHANGED`
 * (public, like `GET /health`), and Milestone 14/15's `MARKET_SNAPSHOT_
 * REFRESHED`/`SIGNIFICANT_MARKET_CHANGE`/`SIGNIFICANT_NEWS_UPDATE` (no
 * per-portfolio scope, no REST source to inherit a permission from). */
const UNGATED_EVENT_TYPES: EventType[] = [
  "HEALTH_STATUS_CHANGED",
  "MARKET_SNAPSHOT_REFRESHED",
  "SIGNIFICANT_MARKET_CHANGE",
  "SIGNIFICANT_NEWS_UPDATE",
];

/** Mirrors `useVisibleFeatureItems` (`src/layouts/sidebar.tsx`) exactly
 * — filters a fixed candidate list by the current user's permissions.
 * `RISK_ASSESSMENT_COMPLETED` is deliberately never included: no REST
 * router publishes it (confirmed gap,
 * `docs/architecture/WEBSOCKET_FRAMEWORK.md` §8), so subscribing would
 * only ever add an inert filter entry. */
// A stable, module-level reference — `state.user?.permissions ?? []`
// would allocate a fresh array on every selector call whenever `user`
// is null, which trips React's `useSyncExternalStore` "getSnapshot
// should be cached" infinite-loop detector (the same M6-established
// footgun documented on `realtime-notification-store.ts`).
const NO_PERMISSIONS: string[] = [];

export function useRealtimeSubscriptions(): EventType[] {
  const permissions = useAuthStore((state) => state.user?.permissions ?? NO_PERMISSIONS);
  const gated = (Object.keys(EVENT_TYPE_PERMISSIONS) as (keyof typeof EVENT_TYPE_PERMISSIONS)[]).filter((type) =>
    permissions.includes(EVENT_TYPE_PERMISSIONS[type]),
  );
  return [...UNGATED_EVENT_TYPES, ...gated];
}
