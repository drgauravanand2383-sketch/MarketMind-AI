import { create } from "zustand";
import { usePreferencesStore } from "@/store/preferences-store";

export type ScreeningProfileSortField = "name" | "created_at" | "updated_at";
export type SortDirection = "asc" | "desc";

interface ScreeningUiState {
  nameSearch: string;
  sort: ScreeningProfileSortField;
  direction: SortDirection;
  page: number;
  pageSize: number;
  setNameSearch: (value: string) => void;
  setSort: (field: ScreeningProfileSortField) => void;
  setPage: (page: number) => void;
}

/** Pure UI state for the screening profiles list — mirrors
 * `watchlist-ui-store.ts`'s scope (what shapes the next query, never the
 * query result itself). Deliberately not persisted. */
export const useScreeningUiStore = create<ScreeningUiState>()((set) => ({
  nameSearch: "",
  sort: "updated_at",
  direction: "desc",
  page: 1,
  // Seeded from the user's global default table page size
  // (`preferences-store.ts`, Milestone 8) at store-creation time.
  pageSize: usePreferencesStore.getState().tables.defaultPageSize,

  setNameSearch: (value) => {
    set({ nameSearch: value, page: 1 });
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
}));
