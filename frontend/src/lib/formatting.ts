import type { NumberFormatLocale, TimezoneDisplay } from "@/types/preferences";

/**
 * Reusable number/date formatting driven by the user's Appearance
 * preferences (`preferences-store.ts`). Scoped to Milestone 8's own
 * surfaces (Profile page, Workspace Settings) rather than retroactively
 * rewiring every existing number/date display across Milestones 2-7 —
 * touching that much already-shipped, already-tested domain code for a
 * cosmetic formatting preference is out of this milestone's scope (see
 * `docs/frontend/MILESTONE_8.md`'s "known limitations"). Any future
 * surface can adopt these two functions directly.
 */
export function formatNumber(value: number, locale: NumberFormatLocale): string {
  return new Intl.NumberFormat(locale).format(value);
}

export function formatDateTime(iso: string, timezoneDisplay: TimezoneDisplay, locale: NumberFormatLocale): string {
  const date = new Date(iso);
  if (timezoneDisplay === "utc") {
    return `${date.toISOString().replace("T", " ").replace(/\.\d+Z$/, "")} UTC`;
  }
  return date.toLocaleString(locale);
}
