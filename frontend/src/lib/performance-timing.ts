/**
 * Minimal boot-timing instrumentation using only the browser's native
 * `Performance` API — no analytics/APM vendor, no new dependency
 * (Milestone 10's "no new telemetry providers" constraint). Named marks
 * show up in the browser DevTools Performance panel and are readable
 * programmatically via `performance.getEntriesByName(...)` — this is
 * the actual "performance timing hook" integration point the app had
 * none of before this milestone.
 */

const BOOT_START_MARK = "marketmind:boot-start";
const APP_SHELL_MOUNTED_MARK = "marketmind:app-shell-mounted";
const BOOT_TO_SHELL_MEASURE = "marketmind:boot-to-shell";

function supportsPerformanceMarks(): boolean {
  return typeof performance !== "undefined" && typeof performance.mark === "function";
}

/** Call once, as early as possible (the first line of `main.tsx`). */
export function markBootStart(): void {
  if (!supportsPerformanceMarks()) return;
  performance.mark(BOOT_START_MARK);
}

/** Call once `AppShell` has completed its first mount — marks the point
 * and, if `markBootStart` ran earlier in this same page load, records a
 * named measure between the two so the duration is directly visible in
 * DevTools without manual arithmetic. */
export function markAppShellMounted(): void {
  if (!supportsPerformanceMarks()) return;
  performance.mark(APP_SHELL_MOUNTED_MARK);
  if (performance.getEntriesByName(BOOT_START_MARK).length === 0) return;
  try {
    performance.measure(BOOT_TO_SHELL_MEASURE, BOOT_START_MARK, APP_SHELL_MOUNTED_MARK);
  } catch {
    // A malformed/missing mark on either side — nothing to measure,
    // nothing to report either. Never let instrumentation break the app.
  }
}
