import type { ReactNode } from "react";

/** A label+control row shared by every Workspace Settings tab — keeps
 * the 6 tabs visually consistent without each re-implementing the same
 * flex layout. */
export function SettingsField({ label, description, children }: { label: string; description?: string; children: ReactNode }): ReactNode {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 py-3 last:border-0 dark:border-slate-800">
      <div>
        <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{label}</p>
        {description && <p className="text-xs text-slate-500 dark:text-slate-400">{description}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}
