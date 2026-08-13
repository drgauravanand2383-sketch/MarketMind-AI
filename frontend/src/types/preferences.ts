import type { NotificationDomain } from "@/store/realtime-notification-store";
import type { PriorityLevel } from "@/components/priority-badge";

/**
 * Milestone 8 preference shapes. Theme mode (`store/theme-store.ts`) and
 * sidebar-collapsed state (`store/ui-store.ts`) are deliberately NOT
 * duplicated here — both already exist as their own persisted stores
 * from earlier milestones; the Workspace Settings UI surfaces them
 * directly rather than re-storing the same value twice.
 */

export type AccentColor = "blue" | "violet" | "green" | "amber" | "rose";
export const ACCENT_COLORS: AccentColor[] = ["blue", "violet", "green", "amber", "rose"];

export type Density = "comfortable" | "compact";

export type TimezoneDisplay = "local" | "utc";

/** A small, fixed set of `Intl.NumberFormat` locales — not an attempt to
 * support every locale, just enough to demonstrate real, working number
 * formatting (see `lib/formatting.ts`). */
export type NumberFormatLocale = "en-US" | "en-GB" | "de-DE" | "fr-FR";
export const NUMBER_FORMAT_LOCALES: NumberFormatLocale[] = ["en-US", "en-GB", "de-DE", "fr-FR"];

export const TABLE_PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;
export type TablePageSize = (typeof TABLE_PAGE_SIZE_OPTIONS)[number];

export interface AppearancePreferences {
  accentColor: AccentColor;
  density: Density;
  /** A route path (e.g. `"/"`, `"/watchlists"`) — where `/` (post-login)
   * redirects the user after sign-in. */
  defaultLandingPage: string;
  timezoneDisplay: TimezoneDisplay;
  numberFormatLocale: NumberFormatLocale;
}

export interface TablePreferences {
  defaultPageSize: TablePageSize;
}

export interface ChartPreferences {
  showDataLabels: boolean;
}

export interface NotificationPreferences {
  toastDurationMs: number;
  defaultPinned: boolean;
  /** UI-only per the milestone spec — no audio actually plays. */
  soundEnabled: boolean;
  /** Gated by the real, permission-aware browser Notification API — see
   * `hooks/use-realtime-sync.ts`. */
  desktopNotificationsEnabled: boolean;
  enabledCategories: NotificationDomain[];
}

export interface AccessibilityPreferences {
  /** Canonical field for both the Accessibility tab's "Reduced motion"
   * and the Appearance tab's "Enable animations" toggle (the same
   * underlying boolean, inverse framing, not two independent fields —
   * see `preferences-store.ts`'s `setAnimationsEnabled`). */
  reducedMotion: boolean;
  highContrast: boolean;
  largeText: boolean;
  focusHighlight: boolean;
}

export type PreferenceSection = "appearance" | "tables" | "charts" | "notifications" | "accessibility";

// --- Dashboard layout (Milestone 8 "Dashboard Customization") -----------------------------------------------------------

export type DashboardCardId =
  | "user"
  | "connectivity"
  | "quick-nav"
  | "realtime-summary"
  | "health-summary-chart"
  | "service-availability-chart"
  | "api-latency-chart"
  | "health-panel"
  | "recent-activity";

export type CardSize = "sm" | "md" | "lg";

export interface DashboardLayout {
  cardOrder: DashboardCardId[];
  hiddenCards: DashboardCardId[];
  cardSizes: Record<DashboardCardId, CardSize>;
}

// --- Saved Views (self-contained to Milestone 8's own settings) -----------------------------------------------------------

export type SavedViewKind = "dashboard-layout" | "chart-defaults" | "notification-filter";

export interface NotificationFilterSnapshot {
  domains: NotificationDomain[];
  readFilter: "all" | "unread" | "read";
  priority: PriorityLevel | "";
  search: string;
}

export interface SavedView {
  id: string;
  name: string;
  kind: SavedViewKind;
  createdAt: string;
  data: DashboardLayout | ChartPreferences | NotificationFilterSnapshot;
}
