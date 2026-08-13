import { create } from "zustand";
import type { PriorityLevel } from "@/components/priority-badge";
import type { EventType } from "@/types/websocket";

export type NotificationDomain = "alerts" | "backtests" | "recommendations" | "strategy" | "explainability" | "health";

/** Only `backtest`/`explainability` carry an id their own detail route
 * can be built from (`request_id`/`run_id`) — `Alert`, `RecommendationResult`,
 * and `StrategyEvaluationResult` all carry no portfolio/watchlist id and
 * have no standalone detail route (both live only as tabs inside
 * `/decisions/$portfolioId`), so those three deliberately have no
 * deep-linkable reference. */
export type NotificationEntityRef =
  | { kind: "alert" }
  | { kind: "recommendation" }
  | { kind: "strategy" }
  | { kind: "backtest"; runId: string }
  | { kind: "explainability"; requestId: string }
  | { kind: "health" };

export interface NotificationCenterEntry {
  id: string;
  eventType: Exclude<EventType, "RISK_ASSESSMENT_COMPLETED">;
  domain: NotificationDomain;
  /** `Alert.priority` passthrough for alerts, derived from
   * `ApplicationHealth.state` for health, `null` for domains with no
   * natural priority concept. */
  priority: PriorityLevel | null;
  title: string;
  summary: string;
  occurredAt: string;
  read: boolean;
  entityRef: NotificationEntityRef;
}

const MAX_ENTRIES = 200;

interface RealtimeNotificationState {
  entries: NotificationCenterEntry[];
  addEntry: (entry: NotificationCenterEntry) => void;
  markRead: (id: string) => void;
  markAllRead: () => void;
  clear: () => void;
}

/**
 * This browser session's own real-time domain events only — never
 * persisted. The backend's WebSocket framework has no message replay or
 * persistence at all (`docs/architecture/WEBSOCKET_FRAMEWORK.md` §6): a
 * client that (re)connects after an event fires simply never sees it, so
 * there is no durable history to back a real one, the same reasoning
 * `session-activity-store.ts` (M4) and `decision-history-store.ts`
 * (M5/M6) already established for their own domains.
 *
 * Scoped to only the 6 real WS-driven domain events plus health status
 * changes (approved product decision, `docs/frontend/MILESTONE_7.md`) —
 * the ~15 pre-existing non-WS `notify()` toast call sites across
 * Milestones 2-6 (CRUD success/failure, form validation, etc.) are never
 * written here.
 *
 * `entries` is a single stable array reference per unchanged state — any
 * consumer deriving a filtered/derived view (e.g. an unread count) MUST
 * select this array and `.filter()`/`.length` in the component body, never
 * inside the Zustand selector itself. Selecting `state.entries.filter(...)`
 * returns a new array reference every render, which trips React's
 * `useSyncExternalStore` "the result of getSnapshot should be cached"
 * infinite-render-loop detector — hit and fixed 4 times already in
 * Milestone 6 (`historical-analysis-history-list.tsx` and others).
 */
export const useRealtimeNotificationStore = create<RealtimeNotificationState>()((set) => ({
  entries: [],

  addEntry: (entry) => {
    set((state) => ({ entries: [entry, ...state.entries].slice(0, MAX_ENTRIES) }));
  },
  markRead: (id) => {
    set((state) => ({ entries: state.entries.map((entry) => (entry.id === id ? { ...entry, read: true } : entry)) }));
  },
  markAllRead: () => {
    set((state) => ({ entries: state.entries.map((entry) => (entry.read ? entry : { ...entry, read: true })) }));
  },
  clear: () => {
    set({ entries: [] });
  },
}));
