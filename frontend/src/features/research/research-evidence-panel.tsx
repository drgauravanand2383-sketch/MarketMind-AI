import type { ReactNode } from "react";
import type { EvidenceReference, NewsReference, RelationshipReference, RiskFlag } from "@/types/research";

function EmptyRow({ message }: { message: string }): ReactNode {
  return <p className="text-sm text-slate-500 dark:text-slate-400">{message}</p>;
}

export function LatestNewsList({ items }: { items: NewsReference[] }): ReactNode {
  if (items.length === 0) return <EmptyRow message="No news references." />;
  return (
    <ul className="flex flex-col gap-2">
      {items.map((item) => (
        <li key={item.record_id} className="border-b border-slate-100 pb-2 text-sm last:border-b-0 dark:border-slate-800/60">
          {item.url ? (
            <a href={item.url} target="_blank" rel="noreferrer" className="font-medium text-brand-700 hover:underline dark:text-brand-400">
              {item.title ?? item.url}
            </a>
          ) : (
            <span className="font-medium text-slate-800 dark:text-slate-200">{item.title ?? "Untitled"}</span>
          )}
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {item.source ?? "Unknown source"}
            {item.published_at && ` · ${new Date(item.published_at).toLocaleDateString()}`}
          </p>
        </li>
      ))}
    </ul>
  );
}

export function SupportingEvidenceList({ items }: { items: EvidenceReference[] }): ReactNode {
  if (items.length === 0) return <EmptyRow message="No supporting evidence records." />;
  return (
    <ul className="flex flex-col gap-2">
      {items.map((item) => (
        <li key={item.record_id} className="border-b border-slate-100 pb-2 text-sm last:border-b-0 dark:border-slate-800/60">
          {item.url ? (
            <a href={item.url} target="_blank" rel="noreferrer" className="font-medium text-brand-700 hover:underline dark:text-brand-400">
              {item.title ?? item.record_id}
            </a>
          ) : (
            <span className="font-medium text-slate-800 dark:text-slate-200">{item.title ?? item.record_id}</span>
          )}
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {[item.provider, item.source].filter(Boolean).join(" · ") || "Unknown provider"}
            {item.published_at && ` · ${new Date(item.published_at).toLocaleDateString()}`}
          </p>
        </li>
      ))}
    </ul>
  );
}

export function RelationshipList({ items }: { items: RelationshipReference[] }): ReactNode {
  if (items.length === 0) return <EmptyRow message="No relationship data." />;
  return (
    <ul className="flex flex-col gap-1.5 text-sm">
      {items.map((item) => (
        <li key={item.related_id} className="flex items-center justify-between gap-2">
          <span className="text-slate-700 dark:text-slate-300">
            {item.related_label} <span className="text-xs text-slate-500 dark:text-slate-400">({item.relationship_type})</span>
          </span>
          <span className="text-xs text-slate-500 dark:text-slate-400">weight {item.weight}</span>
        </li>
      ))}
    </ul>
  );
}

/** These are data-quality/coverage flags about the report itself (per
 * `RiskFlag`'s own backend docstring) — never a market, price, or
 * investment risk assessment. Labeled "Data quality notes" so it can't
 * be mistaken for one. */
export function KeyRisksList({ items }: { items: RiskFlag[] }): ReactNode {
  if (items.length === 0) return <EmptyRow message="No data-quality notes." />;
  return (
    <ul className="flex flex-col gap-1.5 text-sm">
      {items.map((item) => (
        <li key={item.code} className="flex gap-2">
          <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-500/10 dark:text-amber-400">
            {item.code}
          </span>
          <span className="text-slate-700 dark:text-slate-300">{item.description}</span>
        </li>
      ))}
    </ul>
  );
}
