import type { ReactNode } from "react";

export interface PanelProps {
  title?: string;
  children: ReactNode;
}

/** A titled, bordered content section — the one card shape every
 * dashboard/detail-page panel in the app uses, so a panel is never
 * hand-rolled per feature. Omit `title` for a plain bordered container
 * (a panel whose content already has its own heading). */
export function Panel({ title, children }: PanelProps): ReactNode {
  return (
    <section className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      {title && <h2 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-300">{title}</h2>}
      {children}
    </section>
  );
}
