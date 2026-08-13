import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { SortableColumnHeader } from "@/components/table/sortable-column-header";
import { useWatchlistUiStore } from "@/store/watchlist-ui-store";
import type { Watchlist } from "@/types/watchlist";

export interface WatchlistTableProps {
  watchlists: Watchlist[];
  onRename: (watchlist: Watchlist) => void;
  onDuplicate: (watchlist: Watchlist) => void;
  onDelete: (watchlist: Watchlist) => void;
}

interface RowActionsProps {
  watchlist: Watchlist;
  onRename: (watchlist: Watchlist) => void;
  onDuplicate: (watchlist: Watchlist) => void;
  onDelete: (watchlist: Watchlist) => void;
}

function RowActions({ watchlist, onRename, onDuplicate, onDelete }: RowActionsProps): ReactNode {
  return (
    <div className="flex justify-end gap-1">
      <button
        type="button"
        onClick={() => {
          onRename(watchlist);
        }}
        className="rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
      >
        Rename
      </button>
      <button
        type="button"
        onClick={() => {
          onDuplicate(watchlist);
        }}
        className="rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
      >
        Duplicate
      </button>
      <button
        type="button"
        onClick={() => {
          onDelete(watchlist);
        }}
        className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
      >
        Delete
      </button>
    </div>
  );
}

export function WatchlistTable({ watchlists, onRename, onDuplicate, onDelete }: WatchlistTableProps): ReactNode {
  const sort = useWatchlistUiStore((state) => state.sort);
  const direction = useWatchlistUiStore((state) => state.direction);
  const setSort = useWatchlistUiStore((state) => state.setSort);

  return (
    <>
      <table className="hidden w-full text-sm sm:table">
        <caption className="sr-only">Watchlists</caption>
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800">
            <SortableColumnHeader label="Name" field="name" activeField={sort} direction={direction} onSort={setSort} />
            <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
              Companies
            </th>
            <SortableColumnHeader label="Created" field="created_at" activeField={sort} direction={direction} onSort={setSort} />
            <SortableColumnHeader label="Updated" field="updated_at" activeField={sort} direction={direction} onSort={setSort} />
            <th scope="col" className="px-3 py-2 text-right text-xs font-semibold text-slate-500 dark:text-slate-400">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {watchlists.map((watchlist) => (
            <tr key={watchlist.id} className="border-b border-slate-100 dark:border-slate-800/60">
              <td className="px-3 py-2">
                <Link
                  to="/watchlists/$watchlistId"
                  params={{ watchlistId: watchlist.id }}
                  className="font-medium text-brand-700 hover:underline dark:text-brand-400"
                >
                  {watchlist.name}
                </Link>
                {watchlist.description && (
                  <p className="text-xs text-slate-500 dark:text-slate-400">{watchlist.description}</p>
                )}
              </td>
              <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{watchlist.items.length}</td>
              <td className="px-3 py-2 text-slate-500 dark:text-slate-400">
                {new Date(watchlist.created_at).toLocaleDateString()}
              </td>
              <td className="px-3 py-2 text-slate-500 dark:text-slate-400">
                {new Date(watchlist.updated_at).toLocaleDateString()}
              </td>
              <td className="px-3 py-2">
                <RowActions watchlist={watchlist} onRename={onRename} onDuplicate={onDuplicate} onDelete={onDelete} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <ul className="flex flex-col gap-3 sm:hidden">
        {watchlists.map((watchlist) => (
          <li key={watchlist.id} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <Link
                  to="/watchlists/$watchlistId"
                  params={{ watchlistId: watchlist.id }}
                  className="font-medium text-brand-700 hover:underline dark:text-brand-400"
                >
                  {watchlist.name}
                </Link>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {watchlist.items.length} companies · Updated {new Date(watchlist.updated_at).toLocaleDateString()}
                </p>
              </div>
            </div>
            <div className="mt-2">
              <RowActions watchlist={watchlist} onRename={onRename} onDuplicate={onDuplicate} onDelete={onDelete} />
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
