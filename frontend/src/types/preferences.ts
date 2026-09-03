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
  /** v1.2 Priority 4: presentation-only. `true` (default) collapses
   * same-`event_fingerprint` arrivals into one Notification Center row
   * (v1.2 Priority 2's behavior); `false` shows one row per arrival.
   * Never affects server-side suppression, delivery, or how many WS
   * frames arrive — see `store/realtime-notification-store.ts`. */
  groupCrossPortfolioNotifications: boolean;
  /** v1.2 Priority 4: minutes, 1-30, default 5. How long from a decision
   * digest's first change a later different-domain change for the same
   * portfolio still folds into it (v1.2 Priority 3). Locked into each
   * digest at creation (`NotificationCenterEntry.digest.windowMs`) so a
   * setting change mid-window never alters an already-open digest — only
   * digests created after the change use the new value. */
  decisionDigestWindowMinutes: number;
  /** v1.2 Priority 4: presentation-only. `true` (default) shows a toast
   * for real-time events; `false` suppresses only the toast pop-up —
   * Notification Center entries, unread state, and digest/grouping are
   * unaffected. See `hooks/use-realtime-sync.ts`. */
  showRealtimeToasts: boolean;
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
  | "todays-global-markets"
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
