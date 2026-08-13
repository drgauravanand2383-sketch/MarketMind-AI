import { create } from "zustand";
import { persist } from "zustand/middleware";
import { useDashboardLayoutStore } from "@/store/dashboard-layout-store";
import { useNotificationFilterStore } from "@/store/notification-filter-store";
import { usePreferencesStore } from "@/store/preferences-store";
import type { ChartPreferences, DashboardLayout, NotificationFilterSnapshot, SavedView, SavedViewKind } from "@/types/preferences";

interface SavedViewsState {
  views: SavedView[];
  saveView: (name: string, kind: SavedViewKind) => void;
  applyView: (id: string) => void;
  deleteView: (id: string) => void;
  clear: () => void;
}

let nextId = 1;

/**
 * Named, reusable snapshots of Milestone 8's own settings — dashboard
 * layouts, global chart-preference defaults, and the Notification
 * Center's own filters. Deliberately self-contained to what this
 * milestone introduces: the app's only *other* filter UIs live inside
 * investment-domain screens (Screening, Alerts, Watchlists) from earlier
 * milestones, which this milestone's Purpose explicitly says to leave
 * untouched (approved product decision, `docs/frontend/MILESTONE_8.md`).
 * `saveView` captures the *current* live state of the relevant store at
 * the moment it's called — a saved view is a point-in-time snapshot, not
 * a live binding.
 */
export const useSavedViewsStore = create<SavedViewsState>()(
  persist(
    (set, get) => ({
      views: [],

      saveView: (name, kind) => {
        const data = captureCurrentState(kind);
        const id = `saved-view-${String(nextId)}`;
        nextId += 1;
        const view: SavedView = { id, name, kind, createdAt: new Date().toISOString(), data };
        set({ views: [view, ...get().views] });
      },

      applyView: (id) => {
        const view = get().views.find((v) => v.id === id);
        if (!view) return;
        applyToStore(view);
      },

      deleteView: (id) => {
        set({ views: get().views.filter((v) => v.id !== id) });
      },

      clear: () => {
        set({ views: [] });
      },
    }),
    { name: "marketmind-saved-views" },
  ),
);

function captureCurrentState(kind: SavedViewKind): DashboardLayout | ChartPreferences | NotificationFilterSnapshot {
  switch (kind) {
    case "dashboard-layout": {
      const layout = useDashboardLayoutStore.getState();
      return { cardOrder: layout.cardOrder, hiddenCards: layout.hiddenCards, cardSizes: layout.cardSizes };
    }
    case "chart-defaults":
      return { showDataLabels: usePreferencesStore.getState().charts.showDataLabels };
    case "notification-filter": {
      const filters = useNotificationFilterStore.getState();
      return { domains: filters.domains, readFilter: filters.readFilter, priority: filters.priority, search: filters.search };
    }
  }
}

function applyToStore(view: SavedView): void {
  switch (view.kind) {
    case "dashboard-layout":
      useDashboardLayoutStore.getState().applyLayout(view.data as DashboardLayout);
      break;
    case "chart-defaults":
      usePreferencesStore.getState().setShowDataLabels((view.data as ChartPreferences).showDataLabels);
      break;
    case "notification-filter":
      useNotificationFilterStore.getState().applySnapshot(view.data as NotificationFilterSnapshot);
      break;
  }
}

/** "Restore defaults" for one Saved-View kind — resets the underlying
 * live store to its factory default, distinct from applying a user's own
 * saved view. Exported standalone (not a `SavedViewsState` method) since
 * it doesn't touch `views` at all. */
export function restoreDefaultsFor(kind: SavedViewKind): void {
  switch (kind) {
    case "dashboard-layout":
      useDashboardLayoutStore.getState().resetLayout();
      break;
    case "chart-defaults":
      usePreferencesStore.getState().resetSection("charts");
      break;
    case "notification-filter":
      useNotificationFilterStore.getState().resetFilters();
      break;
  }
}

