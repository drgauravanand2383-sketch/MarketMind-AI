import type { ReactNode } from "react";
import { Badge } from "@/components/badge";
import { EmptyState } from "@/components/states/empty-state";
import { NotesCell } from "@/features/watchlists/notes-cell";
import { useMediaQuery } from "@/hooks/use-media-query";
import type { WatchlistItem } from "@/types/watchlist";

// Matches Tailwind's `sm:` breakpoint (640px), the same cutoff the table
// vs. card layout used to switch on via CSS alone.
const DESKTOP_QUERY = "(min-width: 640px)";

export interface CompanyTableProps {
  items: WatchlistItem[];
  onRemove: (ticker: string) => void;
  onSaveNotes: (ticker: string, notes: string) => void;
  removingTicker: string | null;
  savingNotesTicker: string | null;
}

function ConfidenceDisplay({ confidence }: { confidence: number | null }): ReactNode {
  if (confidence === null) return <span className="text-slate-500 dark:text-slate-400">—</span>;
  return <span className="font-medium text-slate-700 dark:text-slate-300">{(confidence * 100).toFixed(0)}%</span>;
}

export function CompanyTable({
  items,
  onRemove,
  onSaveNotes,
  removingTicker,
  savingNotesTicker,
}: CompanyTableProps): ReactNode {
  // Renders exactly one of the two layouts below, not both with one
  // hidden via CSS — the previous `hidden ... sm:table` / `sm:hidden`
  // approach doubled `Watchlist.items`' DOM node count regardless of
  // viewport, since it's fetched unpaginated (Milestone 9 audit finding).
  const isDesktop = useMediaQuery(DESKTOP_QUERY);

  if (items.length === 0) {
    return <EmptyState title="No companies yet" description="Add a company to start tracking it in this watchlist." />;
  }

  if (!isDesktop) {
    return (
      <ul className="flex flex-col gap-3">
        {items.map((item) => (
          <li key={item.ticker} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-medium text-slate-900 dark:text-slate-100">{item.ticker}</p>
                {item.company_name && <p className="text-xs text-slate-500 dark:text-slate-400">{item.company_name}</p>}
              </div>
              <button
                type="button"
                disabled={removingTicker === item.ticker}
                onClick={() => {
                  onRemove(item.ticker);
                }}
                className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:text-red-400 dark:hover:bg-red-950"
              >
                Remove
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {item.sector && <Badge label={item.sector} />}
              {item.country && <Badge label={item.country} />}
              {item.theme && <Badge label={item.theme} />}
            </div>
            <div className="mt-2 flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
              Confidence: <ConfidenceDisplay confidence={item.confidence} />
            </div>
            <div className="mt-2">
              <NotesCell
                ticker={item.ticker}
                notes={item.notes}
                isSaving={savingNotesTicker === item.ticker}
                onSave={onSaveNotes}
              />
            </div>
          </li>
        ))}
      </ul>
    );
  }

  return (
    <table className="w-full text-sm">
      <caption className="sr-only">Companies in this watchlist</caption>
      <thead>
        <tr className="border-b border-slate-200 dark:border-slate-800">
          <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
            Ticker
          </th>
          <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
            Sector
          </th>
          <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
            Country
          </th>
          <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
            Theme
          </th>
          <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
            Confidence
          </th>
          <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
            Notes
          </th>
          <th scope="col" className="px-3 py-2 text-right text-xs font-semibold text-slate-500 dark:text-slate-400">
            Actions
          </th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.ticker} className="border-b border-slate-100 align-top dark:border-slate-800/60">
            <td className="px-3 py-2">
              <p className="font-medium text-slate-900 dark:text-slate-100">{item.ticker}</p>
              {item.company_name && <p className="text-xs text-slate-500 dark:text-slate-400">{item.company_name}</p>}
            </td>
            <td className="px-3 py-2">{item.sector && <Badge label={item.sector} />}</td>
            <td className="px-3 py-2">{item.country && <Badge label={item.country} />}</td>
            <td className="px-3 py-2">{item.theme && <Badge label={item.theme} />}</td>
            <td className="px-3 py-2">
              <ConfidenceDisplay confidence={item.confidence} />
            </td>
            <td className="min-w-48 px-3 py-2">
              <NotesCell
                ticker={item.ticker}
                notes={item.notes}
                isSaving={savingNotesTicker === item.ticker}
                onSave={onSaveNotes}
              />
            </td>
            <td className="px-3 py-2 text-right">
              <button
                type="button"
                disabled={removingTicker === item.ticker}
                onClick={() => {
                  onRemove(item.ticker);
                }}
                className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:text-red-400 dark:hover:bg-red-950"
              >
                Remove
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
