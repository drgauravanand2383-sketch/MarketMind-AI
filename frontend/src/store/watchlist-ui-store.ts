import { create } from "zustand";
import { usePreferencesStore } from "@/store/preferences-store";
import type { SortDirection, WatchlistSortField } from "@/types/watchlist";

export interface WatchlistFilters {
  name: string;
  sector: string;
  country: string;
  theme: string;
  ticker: string;
}

const EMPTY_FILTERS: WatchlistFilters = { name: "", sector: "", country: "", theme: "", ticker: "" };

interface WatchlistUiState {
  filters: WatchlistFilters;
  sort: WatchlistSortField;
  direction: SortDirection;
  page: number;
  pageSize: number;
  /** Collapsed by default below `lg` — the list page expands it on
   * request rather than always showing every filter control on mobile. */
  filtersExpanded: boolean;
  setFilter: (key: keyof WatchlistFilters, value: string) => void;
  setFilters: (filters: WatchlistFilters) => void;
  clearFilters: () => void;
  setSort: (field: WatchlistSortField) => void;
  setPage: (page: number) => void;
  setPageSize: (size: number) => void;
  toggleFiltersExpanded: () => void;
}

/** Pure UI state for the watchlist list page — what the user has typed/
 * selected to shape the next query, never the query result itself
 * (that's `useWatchlistsList`/TanStack Query's job). Deliberately not
 * persisted: reopening the app to a stale filter set would be
 * surprising, not helpful. */
export const useWatchlistUiStore = create<WatchlistUiState>()((set) => ({
  filters: EMPTY_FILTERS,
  sort: "updated_at",
  direction: "desc",
  page: 1,
  // Seeded from the user's global default table page size
  // (`preferences-store.ts`, Milestone 8) at store-creation time — this
  // list's own `setPageSize` still lets the user override it for just
  // this view, same as before.
  pageSize: usePreferencesStore.getState().tables.defaultPageSize,
  filtersExpanded: false,

  setFilter: (key, value) => {
    set((state) => ({ filters: { ...state.filters, [key]: value }, page: 1 }));
  },
  setFilters: (filters) => {
    set({ filters, page: 1 });
  },
  clearFilters: () => {
    set({ filters: EMPTY_FILTERS, page: 1 });
  },
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
  setPageSize: (size) => {
    set({ pageSize: size, page: 1 });
  },
  toggleFiltersExpanded: () => {
    set((state) => ({ filtersExpanded: !state.filtersExpanded }));
  },
}));
