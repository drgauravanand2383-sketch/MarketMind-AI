import { create } from "zustand";
import { usePreferencesStore } from "@/store/preferences-store";

export type AlertSortField = "created_at" | "priority" | "status" | "ticker";
export type SortDirection = "asc" | "desc";

interface AlertsUiState {
  sort: AlertSortField;
  direction: SortDirection;
  page: number;
  pageSize: number;
  /** Client-side only — `GET /alerts` has no filter query params beyond
   * pagination/sort (confirmed against the real router), so priority/
   * status/ticker filtering happens over whatever page is already
   * fetched, not server-side. */
  priorityFilter: string;
  statusFilter: string;
  setSort: (field: AlertSortField) => void;
  setPage: (page: number) => void;
  setPriorityFilter: (value: string) => void;
  setStatusFilter: (value: string) => void;
}

/** Pure UI state for the Alerts list — mirrors `screening-ui-store.ts`'s
 * scope exactly (what shapes the next query/view, never the query result
 * itself). Not persisted. */
export const useAlertsUiStore = create<AlertsUiState>()((set) => ({
  sort: "created_at",
  direction: "desc",
  page: 1,
  // Seeded from the user's global default table page size
  // (`preferences-store.ts`, Milestone 8) at store-creation time.
  pageSize: usePreferencesStore.getState().tables.defaultPageSize,
  priorityFilter: "",
  statusFilter: "",

  setSort: (field) => {
    set((state) => ({
      sort: field,
      direction: state.sort === field && state.direction === "asc" ? "desc" : "asc",
      page: 1,
    }));
  },
  setPage: (page) => {
    set({ page });
  },
  setPriorityFilter: (value) => {
    set({ priorityFilter: value, page: 1 });
  },
  setStatusFilter: (value) => {
    set({ statusFilter: value, page: 1 });
  },
}));
