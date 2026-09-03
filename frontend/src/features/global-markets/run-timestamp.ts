/** The Global Market Intelligence workflow is IST-native — it is
 * scheduled at 08:30 Asia/Kolkata (`cron='30 8 * * *'`,
 * `docs/architecture/GLOBAL_MARKET_INTELLIGENCE.md`) and its audience
 * reads it as "today's" Indian-morning run. So every run-level timestamp
 * this feature shows is rendered in IST, regardless of the viewer's own
 * locale/timezone, with an explicit "IST" suffix so it is never
 * ambiguous. This never mutates or recomputes any stored value — it only
 * formats the `completed_at` / `started_at` ISO string the API already
 * returned. */
const IST_FORMAT = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Kolkata",
});

/** `"12 Feb 2026, 9:05 am IST"` — or `null` for a missing/invalid input
 * (e.g. a still-running run whose `completed_at` is `null`). */
export function formatRunTimestampIst(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return `${IST_FORMAT.format(date)} IST`;
}

/** Whole days between `runDate` (a `YYYY-MM-DD` string) and today, in the
 * viewer's local calendar — used to flag a stale run ("last run 3 days
 * ago") on the dashboard card. Negative/NaN inputs yield `0`. */
export function daysSinceRunDate(runDate: string, now: Date = new Date()): number {
  const parsed = new Date(`${runDate}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return 0;
  const todayMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diffMs = todayMidnight.getTime() - parsed.getTime();
  return Math.max(0, Math.floor(diffMs / 86_400_000));
}
