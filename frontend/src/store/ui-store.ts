import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UiState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  mobileNavOpen: boolean;
  setMobileNavOpen: (open: boolean) => void;
}

/** Sidebar collapse is a durable preference (persisted); the mobile nav
 * drawer's open/closed state is purely transient UI state for the
 * current view and is deliberately not persisted — reopening the app
 * with yesterday's mobile drawer left open would be a bug, not a feature. */
export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      toggleSidebar: () => {
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed }));
      },
      mobileNavOpen: false,
      setMobileNavOpen: (open) => {
        set({ mobileNavOpen: open });
      },
    }),
    {
      name: "marketmind-ui",
      partialize: (state) => ({ sidebarCollapsed: state.sidebarCollapsed }),
    },
  ),
);
