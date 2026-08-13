import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ShortcutAction =
  | "search"
  | "help"
  | "goToDashboard"
  | "goToWatchlists"
  | "goToDecisionCenter"
  | "goToHistoricalAnalysis"
  | "goToNotifications"
  | "goToSettings";

export interface ShortcutDefinition {
  action: ShortcutAction;
  label: string;
  defaultKey: string;
}

/** "Search" focuses the current page's own existing search/filter input
 * (tagged `data-shortcut-target="search"`) rather than opening a new
 * command-palette overlay — approved product decision, since a global
 * search feature doesn't exist anywhere in the app today and the
 * Milestone 9 spec's own Purpose statement rules out new business
 * functionality. */
export const SHORTCUT_DEFINITIONS: ShortcutDefinition[] = [
  { action: "search", label: "Focus this page's search", defaultKey: "/" },
  { action: "help", label: "Show keyboard shortcuts", defaultKey: "?" },
  { action: "goToDashboard", label: "Go to Dashboard", defaultKey: "d" },
  { action: "goToWatchlists", label: "Go to Watchlists", defaultKey: "w" },
  { action: "goToDecisionCenter", label: "Go to Decision Center", defaultKey: "c" },
  { action: "goToHistoricalAnalysis", label: "Go to Historical Analysis", defaultKey: "h" },
  { action: "goToNotifications", label: "Go to Notifications", defaultKey: "n" },
  { action: "goToSettings", label: "Go to Settings", defaultKey: "s" },
];

const DEFAULT_BINDINGS: Record<ShortcutAction, string> = Object.fromEntries(
  SHORTCUT_DEFINITIONS.map((definition) => [definition.action, definition.defaultKey]),
) as Record<ShortcutAction, string>;

interface ShortcutsState {
  bindings: Record<ShortcutAction, string>;
  /** Not persisted (`partialize` below) — reopening the app already
   * showing the help dialog would be surprising, same reasoning
   * `dashboard-layout-store.ts`'s `isCustomizing` already established. */
  helpOpen: boolean;
  setBinding: (action: ShortcutAction, key: string) => void;
  resetBinding: (action: ShortcutAction) => void;
  resetAll: () => void;
  openHelp: () => void;
  closeHelp: () => void;
}

/** User-configurable keyboard shortcuts (Milestone 9 "Keyboard
 * Productivity"). Rebinding happens in Workspace Settings' Shortcuts
 * tab; the live keydown listener lives in `use-keyboard-shortcuts.ts`. */
export const useShortcutsStore = create<ShortcutsState>()(
  persist(
    (set) => ({
      bindings: DEFAULT_BINDINGS,
      helpOpen: false,

      setBinding: (action, key) => {
        set((state) => ({ bindings: { ...state.bindings, [action]: key } }));
      },

      resetBinding: (action) => {
        set((state) => ({ bindings: { ...state.bindings, [action]: DEFAULT_BINDINGS[action] } }));
      },

      resetAll: () => {
        set({ bindings: DEFAULT_BINDINGS });
      },

      openHelp: () => {
        set({ helpOpen: true });
      },

      closeHelp: () => {
        set({ helpOpen: false });
      },
    }),
    {
      name: "marketmind-shortcuts",
      partialize: (state) => ({ bindings: state.bindings }),
    },
  ),
);
