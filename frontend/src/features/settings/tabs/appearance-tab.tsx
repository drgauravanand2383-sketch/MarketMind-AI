import type { ReactNode } from "react";
import { ThemeToggle } from "@/components/theme-toggle";
import { SegmentedControl } from "@/components/segmented-control";
import { SettingsField } from "@/features/settings/settings-field";
import { usePreferencesStore } from "@/store/preferences-store";
import { useUiStore } from "@/store/ui-store";
import { ACCENT_COLORS, NUMBER_FORMAT_LOCALES } from "@/types/preferences";
import type { AccentColor } from "@/types/preferences";

const ACCENT_SWATCH_CLASS: Record<AccentColor, string> = {
  blue: "bg-blue-600",
  violet: "bg-violet-600",
  green: "bg-green-600",
  amber: "bg-amber-500",
  rose: "bg-rose-600",
};

const LANDING_PAGE_OPTIONS = [
  { value: "/", label: "Dashboard" },
  { value: "/watchlists", label: "Watchlists" },
  { value: "/research", label: "Research" },
  { value: "/screening", label: "Screening" },
  { value: "/decisions", label: "Decision Center" },
  { value: "/historical-analysis", label: "Historical Analysis" },
  { value: "/notifications", label: "Notifications" },
];

export function AppearanceTab(): ReactNode {
  const accentColor = usePreferencesStore((state) => state.appearance.accentColor);
  const density = usePreferencesStore((state) => state.appearance.density);
  const defaultLandingPage = usePreferencesStore((state) => state.appearance.defaultLandingPage);
  const timezoneDisplay = usePreferencesStore((state) => state.appearance.timezoneDisplay);
  const numberFormatLocale = usePreferencesStore((state) => state.appearance.numberFormatLocale);
  const setAccentColor = usePreferencesStore((state) => state.setAccentColor);
  const setDensity = usePreferencesStore((state) => state.setDensity);
  const setDefaultLandingPage = usePreferencesStore((state) => state.setDefaultLandingPage);
  const setTimezoneDisplay = usePreferencesStore((state) => state.setTimezoneDisplay);
  const setNumberFormatLocale = usePreferencesStore((state) => state.setNumberFormatLocale);

  const reducedMotion = usePreferencesStore((state) => state.accessibility.reducedMotion);
  const setReducedMotion = usePreferencesStore((state) => state.setReducedMotion);

  const sidebarCollapsed = useUiStore((state) => state.sidebarCollapsed);
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);

  return (
    <div className="flex flex-col">
      <SettingsField label="Theme">
        <ThemeToggle />
      </SettingsField>

      <SettingsField label="Accent color">
        <div role="radiogroup" aria-label="Accent color" className="flex gap-2">
          {ACCENT_COLORS.map((color) => (
            <button
              key={color}
              type="button"
              role="radio"
              aria-checked={accentColor === color}
              aria-label={color}
              onClick={() => {
                setAccentColor(color);
              }}
              className={`h-6 w-6 rounded-full ${ACCENT_SWATCH_CLASS[color]} ${accentColor === color ? "ring-2 ring-offset-2 ring-slate-900 dark:ring-offset-slate-950 dark:ring-slate-100" : ""}`}
            />
          ))}
        </div>
      </SettingsField>

      <SettingsField label="Density" description="Compact reduces spacing in lists and tables.">
        <SegmentedControl
          label="Density"
          value={density}
          onChange={setDensity}
          options={[
            { value: "comfortable", label: "Comfortable" },
            { value: "compact", label: "Compact" },
          ]}
        />
      </SettingsField>

      <SettingsField label="Enable animations" description="Also controlled from the Accessibility tab's Reduced motion toggle.">
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input
            type="checkbox"
            checked={!reducedMotion}
            onChange={(event) => {
              setReducedMotion(!event.target.checked);
            }}
          />
          Animations
        </label>
      </SettingsField>

      <SettingsField label="Sidebar collapsed">
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input type="checkbox" checked={sidebarCollapsed} onChange={toggleSidebar} />
          Collapsed by default
        </label>
      </SettingsField>

      <SettingsField label="Default landing page" description="Where the app opens after you sign in.">
        <label className="sr-only" htmlFor="default-landing-page">
          Default landing page
        </label>
        <select
          id="default-landing-page"
          value={defaultLandingPage}
          onChange={(event) => {
            setDefaultLandingPage(event.target.value);
          }}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        >
          {LANDING_PAGE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </SettingsField>

      <SettingsField label="Timezone display">
        <SegmentedControl
          label="Timezone display"
          value={timezoneDisplay}
          onChange={setTimezoneDisplay}
          options={[
            { value: "local", label: "Local" },
            { value: "utc", label: "UTC" },
          ]}
        />
      </SettingsField>

      <SettingsField label="Number format">
        <label className="sr-only" htmlFor="number-format-locale">
          Number format
        </label>
        <select
          id="number-format-locale"
          value={numberFormatLocale}
          onChange={(event) => {
            setNumberFormatLocale(event.target.value as (typeof NUMBER_FORMAT_LOCALES)[number]);
          }}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        >
          {NUMBER_FORMAT_LOCALES.map((locale) => (
            <option key={locale} value={locale}>
              {locale}
            </option>
          ))}
        </select>
      </SettingsField>
    </div>
  );
}
