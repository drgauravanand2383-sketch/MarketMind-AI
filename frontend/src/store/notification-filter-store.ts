import { create } from "zustand";
import type { PriorityLevel } from "@/components/priority-badge";
import type { NotificationDomain } from "@/store/realtime-notification-store";
import type { NotificationFilterSnapshot } from "@/types/preferences";

export type NotificationReadFilter = "all" | "unread" | "read";

export const ALL_NOTIFICATION_DOMAINS: NotificationDomain[] = [
  "alerts", "backtests", "recommendations", "strategy", "explainability", "health", "market", "news", "decisions",
];

interface NotificationFilterState {
  domains: NotificationDomain[];
  readFilter: NotificationReadFilter;
  priority: PriorityLevel | "";
  search: string;
  toggleDomain: (domain: NotificationDomain) => void;
  setReadFilter: (value: NotificationReadFilter) => void;
  setPriority: (value: PriorityLevel | "") => void;
  setSearch: (value: string) => void;
  applySnapshot: (snapshot: NotificationFilterSnapshot) => void;
  resetFilters: () => void;
}

const DEFAULT_FILTERS: NotificationFilterSnapshot = { domains: ALL_NOTIFICATION_DOMAINS, readFilter: "all", priority: "", search: "" };

/**
 * The Notification Center page's own filter state — lifted out of local
 * `useState` (Milestone 7) into a store so it's both a) the page's
 * filter UI state and b) a real, capturable/restorable payload for the
 * "notification-filter" kind of `SavedView` (Milestone 8, approved
 * self-contained scope — see `docs/frontend/MILESTONE_8.md`). This is
 * Milestone 7's own page, not an investment-domain feature, so lifting
 * its state is in-scope. Session-only, not persisted — matches
 * `realtime-notification-store.ts`'s own non-persistence (the data being
 * filtered is itself never durable).
 */
export const useNotificationFilterStore = create<NotificationFilterState>()((set) => ({
  ...DEFAULT_FILTERS,

  toggleDomain: (domain) => {
    set((state) => ({ domains: state.domains.includes(domain) ? state.domains.filter((d) => d !== domain) : [...state.domains, domain] }));
  },
  setReadFilter: (readFilter) => {
    set({ readFilter });
  },
  setPriority: (priority) => {
    set({ priority });
  },
  setSearch: (search) => {
    set({ search });
  },
  applySnapshot: (snapshot) => {
    set({ ...snapshot });
  },
  resetFilters: () => {
    set({ ...DEFAULT_FILTERS });
  },
}));
