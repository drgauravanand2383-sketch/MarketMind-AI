import type { ReactNode } from "react";

const FORMATS = ["PDF", "CSV", "JSON"] as const;

/** Inert UI placeholders only — no backend export endpoint exists for
 * any format (confirmed absent across the entire API surface,
 * `docs/frontend/MILESTONE_6.md`), and the spec explicitly says not to
 * implement one unless the backend already supports it. Each button is
 * `disabled` with a title explaining why, never silently doing nothing
 * on click. */
export function ExportPlaceholderMenu(): ReactNode {
  return (
    <div role="group" aria-label="Export (not yet available)" className="flex gap-1">
      {FORMATS.map((format) => (
        <button
          key={format}
          type="button"
          disabled
          title={`Export to ${format} isn't implemented yet — no backend endpoint exists for it.`}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-400 dark:border-slate-700 dark:text-slate-600"
        >
          {format}
        </button>
      ))}
    </div>
  );
}
