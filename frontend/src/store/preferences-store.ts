import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { NotificationDomain } from "@/store/realtime-notification-store";
import type {
  AccentColor,
  AccessibilityPreferences,
  AppearancePreferences,
  ChartPreferences,
  Density,
  NotificationPreferences,
  NumberFormatLocale,
  PreferenceSection,
  TablePageSize,
  TablePreferences,
  TimezoneDisplay,
} from "@/types/preferences";

const DEFAULT_APPEARANCE: AppearancePreferences = {
  accentColor: "blue",
  density: "comfortable",
  defaultLandingPage: "/",
  timezoneDisplay: "local",
  numberFormatLocale: "en-US",
};

const DEFAULT_TABLES: TablePreferences = {
  defaultPageSize: 20,
};

const DEFAULT_CHARTS: ChartPreferences = {
  showDataLabels: false,
};

const ALL_NOTIFICATION_DOMAINS: NotificationDomain[] = [
  "alerts", "backtests", "recommendations", "strategy", "explainability", "health", "market", "news", "decisions",
];

const DEFAULT_NOTIFICATIONS: NotificationPreferences = {
  toastDurationMs: 6_000,
  defaultPinned: false,
  soundEnabled: false,
  desktopNotificationsEnabled: false,
  enabledCategories: ALL_NOTIFICATION_DOMAINS,
};

const DEFAULT_ACCESSIBILITY: AccessibilityPreferences = {
  reducedMotion: false,
  highContrast: false,
  largeText: false,
  focusHighlight: false,
};

interface PreferencesState {
  appearance: AppearancePreferences;
  tables: TablePreferences;
  charts: ChartPreferences;
  notifications: NotificationPreferences;
  accessibility: AccessibilityPreferences;

  setAccentColor: (color: AccentColor) => void;
  setDensity: (density: Density) => void;
  setDefaultLandingPage: (path: string) => void;
  setTimezoneDisplay: (value: TimezoneDisplay) => void;
  setNumberFormatLocale: (locale: NumberFormatLocale) => void;

  setDefaultPageSize: (size: TablePageSize) => void;

  setShowDataLabels: (show: boolean) => void;

  setToastDurationMs: (ms: number) => void;
  setDefaultPinned: (pinned: boolean) => void;
  setSoundEnabled: (enabled: boolean) => void;
  setDesktopNotificationsEnabled: (enabled: boolean) => void;
  toggleNotificationCategory: (domain: NotificationDomain) => void;

  /** Also the "Enable animations" toggle on the Appearance tab, inverse-
   * framed — one canonical field, no duplicate state to drift. */
  setReducedMotion: (reduced: boolean) => void;
  setHighContrast: (value: boolean) => void;
  setLargeText: (value: boolean) => void;
  setFocusHighlight: (value: boolean) => void;

  resetSection: (section: PreferenceSection) => void;
  resetAll: () => void;
}

/**
 * All Milestone 8 user preferences except theme mode (`theme-store.ts`)
 * and sidebar-collapsed state (`ui-store.ts`), both already their own
 * persisted stores from earlier milestones — never duplicated here.
 * Persisted via Zustand's `persist` middleware to `localStorage` only
 * (no "remember me" distinction like `auth-store.ts` — preferences carry
 * no sensitive data and should always survive a closed browser, per the
 * milestone's explicit "No backend persistence... Zustand persistence"
 * instruction). This is also the exact shape `lib/preferences-io.ts`
 * exports/imports as JSON.
 */
export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set) => ({
      appearance: DEFAULT_APPEARANCE,
      tables: DEFAULT_TABLES,
      charts: DEFAULT_CHARTS,
      notifications: DEFAULT_NOTIFICATIONS,
      accessibility: DEFAULT_ACCESSIBILITY,

      setAccentColor: (accentColor) => {
        set((state) => ({ appearance: { ...state.appearance, accentColor } }));
      },
      setDensity: (density) => {
        set((state) => ({ appearance: { ...state.appearance, density } }));
      },
      setDefaultLandingPage: (defaultLandingPage) => {
        set((state) => ({ appearance: { ...state.appearance, defaultLandingPage } }));
      },
      setTimezoneDisplay: (timezoneDisplay) => {
        set((state) => ({ appearance: { ...state.appearance, timezoneDisplay } }));
      },
      setNumberFormatLocale: (numberFormatLocale) => {
        set((state) => ({ appearance: { ...state.appearance, numberFormatLocale } }));
      },

      setDefaultPageSize: (defaultPageSize) => {
        set({ tables: { defaultPageSize } });
      },

      setShowDataLabels: (showDataLabels) => {
        set({ charts: { showDataLabels } });
      },

      setToastDurationMs: (toastDurationMs) => {
        set((state) => ({ notifications: { ...state.notifications, toastDurationMs } }));
      },
      setDefaultPinned: (defaultPinned) => {
        set((state) => ({ notifications: { ...state.notifications, defaultPinned } }));
      },
      setSoundEnabled: (soundEnabled) => {
        set((state) => ({ notifications: { ...state.notifications, soundEnabled } }));
      },
      setDesktopNotificationsEnabled: (desktopNotificationsEnabled) => {
        set((state) => ({ notifications: { ...state.notifications, desktopNotificationsEnabled } }));
      },
      toggleNotificationCategory: (domain) => {
        set((state) => {
          const current = state.notifications.enabledCategories;
          const enabledCategories = current.includes(domain) ? current.filter((d) => d !== domain) : [...current, domain];
          return { notifications: { ...state.notifications, enabledCategories } };
        });
      },

      setReducedMotion: (reducedMotion) => {
        set((state) => ({ accessibility: { ...state.accessibility, reducedMotion } }));
      },
      setHighContrast: (highContrast) => {
        set((state) => ({ accessibility: { ...state.accessibility, highContrast } }));
      },
      setLargeText: (largeText) => {
        set((state) => ({ accessibility: { ...state.accessibility, largeText } }));
      },
      setFocusHighlight: (focusHighlight) => {
        set((state) => ({ accessibility: { ...state.accessibility, focusHighlight } }));
      },

      resetSection: (section) => {
        switch (section) {
          case "appearance":
            set({ appearance: DEFAULT_APPEARANCE });
            break;
          case "tables":
            set({ tables: DEFAULT_TABLES });
            break;
          case "charts":
            set({ charts: DEFAULT_CHARTS });
            break;
          case "notifications":
            set({ notifications: DEFAULT_NOTIFICATIONS });
            break;
          case "accessibility":
            set({ accessibility: DEFAULT_ACCESSIBILITY });
            break;
        }
      },
      resetAll: () => {
        set({
          appearance: DEFAULT_APPEARANCE,
          tables: DEFAULT_TABLES,
          charts: DEFAULT_CHARTS,
          notifications: DEFAULT_NOTIFICATIONS,
          accessibility: DEFAULT_ACCESSIBILITY,
        });
      },
    }),
    { name: "marketmind-preferences" },
  ),
);
