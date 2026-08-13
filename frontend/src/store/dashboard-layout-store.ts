import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { CardSize, DashboardCardId, DashboardLayout } from "@/types/preferences";

export const DEFAULT_CARD_ORDER: DashboardCardId[] = [
  "user",
  "connectivity",
  "quick-nav",
  "realtime-summary",
  "health-summary-chart",
  "service-availability-chart",
  "api-latency-chart",
  "health-panel",
  "recent-activity",
];

const DEFAULT_CARD_SIZES: Record<DashboardCardId, CardSize> = {
  user: "sm",
  connectivity: "lg",
  "quick-nav": "lg",
  "realtime-summary": "lg",
  "health-summary-chart": "md",
  "service-availability-chart": "md",
  "api-latency-chart": "lg",
  "health-panel": "md",
  "recent-activity": "md",
};

const DEFAULT_LAYOUT: DashboardLayout = {
  cardOrder: DEFAULT_CARD_ORDER,
  hiddenCards: [],
  cardSizes: DEFAULT_CARD_SIZES,
};

interface DashboardLayoutState extends DashboardLayout {
  /** Toggled by a "Customize dashboard" button — only in this mode do
   * per-card move/hide/resize controls render, so the everyday dashboard
   * stays uncluttered. Deliberately not persisted (`partialize` below) —
   * reopening the app already "in edit mode" would be surprising. */
  isCustomizing: boolean;
  toggleCustomizing: () => void;
  moveCardUp: (id: DashboardCardId) => void;
  moveCardDown: (id: DashboardCardId) => void;
  toggleCardVisibility: (id: DashboardCardId) => void;
  cycleCardSize: (id: DashboardCardId) => void;
  resetLayout: () => void;
  applyLayout: (layout: DashboardLayout) => void;
}

const SIZE_CYCLE: CardSize[] = ["sm", "md", "lg"];

function swap<T>(items: T[], indexA: number, indexB: number): T[] {
  const next = [...items];
  const a = next[indexA];
  const b = next[indexB];
  if (a === undefined || b === undefined) return items;
  next[indexA] = b;
  next[indexB] = a;
  return next;
}

/**
 * Dashboard card order/visibility/size — Milestone 8 "Dashboard
 * Customization." Reordering/resizing uses plain Move up/down and a
 * size-cycle button rather than drag-and-drop (approved product
 * decision, `docs/frontend/MILESTONE_8.md`) — no new dependency, fully
 * keyboard-accessible by default. Persisted separately from
 * `preferences-store.ts` since the spec calls out "Persist layout
 * locally" as its own concern, distinct from general preferences, and
 * because "Reset dashboard layout" should reset only this, not every
 * preference.
 */
export const useDashboardLayoutStore = create<DashboardLayoutState>()(
  persist(
    (set, get) => ({
      ...DEFAULT_LAYOUT,
      isCustomizing: false,

      toggleCustomizing: () => {
        set((state) => ({ isCustomizing: !state.isCustomizing }));
      },

      moveCardUp: (id) => {
        const order = get().cardOrder;
        const index = order.indexOf(id);
        if (index <= 0) return;
        set({ cardOrder: swap(order, index, index - 1) });
      },

      moveCardDown: (id) => {
        const order = get().cardOrder;
        const index = order.indexOf(id);
        if (index === -1 || index >= order.length - 1) return;
        set({ cardOrder: swap(order, index, index + 1) });
      },

      toggleCardVisibility: (id) => {
        const hidden = get().hiddenCards;
        set({ hiddenCards: hidden.includes(id) ? hidden.filter((cardId) => cardId !== id) : [...hidden, id] });
      },

      cycleCardSize: (id) => {
        const current = get().cardSizes[id];
        const nextIndex = (SIZE_CYCLE.indexOf(current) + 1) % SIZE_CYCLE.length;
        const nextSize = SIZE_CYCLE[nextIndex] ?? "sm";
        set((state) => ({ cardSizes: { ...state.cardSizes, [id]: nextSize } }));
      },

      resetLayout: () => {
        set({ ...DEFAULT_LAYOUT });
      },

      applyLayout: (layout) => {
        set({ ...layout });
      },
    }),
    {
      name: "marketmind-dashboard-layout",
      partialize: (state) => ({ cardOrder: state.cardOrder, hiddenCards: state.hiddenCards, cardSizes: state.cardSizes }),
    },
  ),
);
