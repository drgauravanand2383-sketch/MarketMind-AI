import { z } from "zod";
import { useThemeStore, applyTheme } from "@/store/theme-store";
import { useUiStore } from "@/store/ui-store";
import { usePreferencesStore } from "@/store/preferences-store";
import { useDashboardLayoutStore } from "@/store/dashboard-layout-store";
import { useSavedViewsStore } from "@/store/saved-views-store";
import { ACCENT_COLORS, NUMBER_FORMAT_LOCALES, TABLE_PAGE_SIZE_OPTIONS } from "@/types/preferences";
import type { AccentColor, NumberFormatLocale, TablePageSize } from "@/types/preferences";

export const PREFERENCES_EXPORT_VERSION = 1;

const themeModeSchema = z.enum(["light", "dark", "system"]);
const accentColorSchema = z.enum(ACCENT_COLORS as [AccentColor, ...AccentColor[]]);
const densitySchema = z.enum(["comfortable", "compact"]);
const timezoneDisplaySchema = z.enum(["local", "utc"]);
const numberFormatLocaleSchema = z.enum(NUMBER_FORMAT_LOCALES as [NumberFormatLocale, ...NumberFormatLocale[]]);
const tablePageSizeSchema = z.union(
  TABLE_PAGE_SIZE_OPTIONS.map((size) => z.literal(size)) as [z.ZodLiteral<TablePageSize>, ...z.ZodLiteral<TablePageSize>[]],
);
const notificationDomainSchema = z.enum(["alerts", "backtests", "recommendations", "strategy", "explainability", "health"]);
const cardSizeSchema = z.enum(["sm", "md", "lg"]);
const dashboardCardIdSchema = z.enum([
  "user",
  "connectivity",
  "quick-nav",
  "realtime-summary",
  "health-summary-chart",
  "service-availability-chart",
  "api-latency-chart",
  "health-panel",
  "recent-activity",
]);
const savedViewKindSchema = z.enum(["dashboard-layout", "chart-defaults", "notification-filter"]);
const priorityLevelSchema = z.union([z.enum(["LOW", "MODERATE", "MEDIUM", "HIGH", "CRITICAL"]), z.literal("")]);

const dashboardLayoutSchema = z.object({
  cardOrder: z.array(dashboardCardIdSchema),
  hiddenCards: z.array(dashboardCardIdSchema),
  cardSizes: z.record(dashboardCardIdSchema, cardSizeSchema),
});

const chartDefaultsSchema = z.object({ showDataLabels: z.boolean() });

const notificationFilterSchema = z.object({
  domains: z.array(notificationDomainSchema),
  readFilter: z.enum(["all", "unread", "read"]),
  priority: priorityLevelSchema,
  search: z.string(),
});

const savedViewSchema = z.object({
  id: z.string(),
  name: z.string(),
  kind: savedViewKindSchema,
  createdAt: z.string(),
  data: z.union([dashboardLayoutSchema, chartDefaultsSchema, notificationFilterSchema]),
});

/** The single exported/imported JSON document — every user-configurable
 * value Milestone 8 introduces, plus the two pre-existing persisted
 * stores (theme, sidebar) it deliberately doesn't duplicate. Validated
 * with `zod` (already a project dependency, no new one added) *before*
 * anything is written to any store — an invalid file therefore can never
 * partially apply ("rollback on invalid import" is satisfied by simply
 * never starting). */
export const preferencesExportSchema = z.object({
  version: z.literal(PREFERENCES_EXPORT_VERSION),
  exportedAt: z.string(),
  theme: z.object({ mode: themeModeSchema }),
  ui: z.object({ sidebarCollapsed: z.boolean() }),
  preferences: z.object({
    appearance: z.object({
      accentColor: accentColorSchema,
      density: densitySchema,
      defaultLandingPage: z.string(),
      timezoneDisplay: timezoneDisplaySchema,
      numberFormatLocale: numberFormatLocaleSchema,
    }),
    tables: z.object({ defaultPageSize: tablePageSizeSchema }),
    charts: chartDefaultsSchema,
    notifications: z.object({
      toastDurationMs: z.number().nonnegative(),
      defaultPinned: z.boolean(),
      soundEnabled: z.boolean(),
      desktopNotificationsEnabled: z.boolean(),
      enabledCategories: z.array(notificationDomainSchema),
    }),
    accessibility: z.object({
      reducedMotion: z.boolean(),
      highContrast: z.boolean(),
      largeText: z.boolean(),
      focusHighlight: z.boolean(),
    }),
  }),
  dashboardLayout: dashboardLayoutSchema,
  savedViews: z.array(savedViewSchema),
});

export type PreferencesExport = z.infer<typeof preferencesExportSchema>;

export function buildPreferencesExport(): PreferencesExport {
  const theme = useThemeStore.getState();
  const ui = useUiStore.getState();
  const preferences = usePreferencesStore.getState();
  const dashboardLayout = useDashboardLayoutStore.getState();
  const savedViews = useSavedViewsStore.getState();

  return {
    version: PREFERENCES_EXPORT_VERSION,
    exportedAt: new Date().toISOString(),
    theme: { mode: theme.mode },
    ui: { sidebarCollapsed: ui.sidebarCollapsed },
    preferences: {
      appearance: preferences.appearance,
      tables: preferences.tables,
      charts: preferences.charts,
      notifications: preferences.notifications,
      accessibility: preferences.accessibility,
    },
    dashboardLayout: { cardOrder: dashboardLayout.cardOrder, hiddenCards: dashboardLayout.hiddenCards, cardSizes: dashboardLayout.cardSizes },
    savedViews: savedViews.views,
  };
}

/** Triggers a real browser download — a `Blob`+`URL.createObjectURL`
 * anchor click, no server round trip and no new dependency. */
export function downloadPreferencesExport(): void {
  const data = buildPreferencesExport();
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `marketmind-preferences-${new Date().toISOString().slice(0, 10)}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export type ImportResult = { success: true } | { success: false; error: string };

/**
 * Validates first, writes second — an invalid/malformed file is
 * rejected with a readable error and **nothing is written to any
 * store**, satisfying "rollback on invalid import" by construction
 * rather than needing an explicit undo step.
 */
export function importPreferencesFromJson(raw: string): ImportResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { success: false, error: "That file isn't valid JSON." };
  }

  const result = preferencesExportSchema.safeParse(parsed);
  if (!result.success) {
    return { success: false, error: `That file doesn't match the expected preferences format: ${result.error.issues[0]?.message ?? "unknown validation error"}.` };
  }

  applyPreferencesExport(result.data);
  return { success: true };
}

function applyPreferencesExport(data: PreferencesExport): void {
  useThemeStore.setState({ mode: data.theme.mode });
  applyTheme(data.theme.mode);
  useUiStore.setState({ sidebarCollapsed: data.ui.sidebarCollapsed });
  usePreferencesStore.setState({
    appearance: data.preferences.appearance,
    tables: data.preferences.tables,
    charts: data.preferences.charts,
    notifications: data.preferences.notifications,
    accessibility: data.preferences.accessibility,
  });
  useDashboardLayoutStore.setState({
    cardOrder: data.dashboardLayout.cardOrder,
    hiddenCards: data.dashboardLayout.hiddenCards,
    cardSizes: data.dashboardLayout.cardSizes,
  });
  useSavedViewsStore.setState({ views: data.savedViews });
}
