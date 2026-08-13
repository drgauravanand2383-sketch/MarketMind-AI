import { useEffect, useState, type ReactNode } from "react";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useWatchlistUiStore, type WatchlistFilters } from "@/store/watchlist-ui-store";

const FILTER_FIELDS: { key: keyof WatchlistFilters; label: string; placeholder: string }[] = [
  { key: "sector", label: "Sector", placeholder: "e.g. Technology" },
  { key: "country", label: "Country", placeholder: "e.g. US" },
  { key: "theme", label: "Theme", placeholder: "e.g. AI" },
  { key: "ticker", label: "Ticker", placeholder: "e.g. AAPL" },
];

const INPUT_CLASS =
  "rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100";

export function WatchlistFiltersBar(): ReactNode {
  const storeFilters = useWatchlistUiStore((state) => state.filters);
  const setFilters = useWatchlistUiStore((state) => state.setFilters);
  const clearFilters = useWatchlistUiStore((state) => state.clearFilters);
  const filtersExpanded = useWatchlistUiStore((state) => state.filtersExpanded);
  const toggleFiltersExpanded = useWatchlistUiStore((state) => state.toggleFiltersExpanded);

  const [localFilters, setLocalFilters] = useState(storeFilters);
  const debouncedFilters = useDebouncedValue(localFilters);

  useEffect(() => {
    setFilters(debouncedFilters);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- setFilters is a stable store action
  }, [debouncedFilters]);

  const activeCount = [storeFilters.name, storeFilters.sector, storeFilters.country, storeFilters.theme, storeFilters.ticker].filter(
    (value) => value.length > 0,
  ).length;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="watchlist-search" className="sr-only">
          Search watchlists by name
        </label>
        <input
          id="watchlist-search"
          type="search"
          data-shortcut-target="search"
          placeholder="Search watchlists…"
          value={localFilters.name}
          onChange={(event) => {
            setLocalFilters((prev) => ({ ...prev, name: event.target.value }));
          }}
          className={`${INPUT_CLASS} min-w-0 flex-1`}
        />
        <button
          type="button"
          onClick={toggleFiltersExpanded}
          aria-expanded={filtersExpanded}
          aria-controls="watchlist-filter-panel"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 lg:hidden dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Filters{activeCount > 0 ? ` (${String(activeCount)})` : ""}
        </button>
      </div>

      <div
        id="watchlist-filter-panel"
        className={`${filtersExpanded ? "flex" : "hidden"} flex-wrap items-end gap-3 lg:flex`}
      >
        {FILTER_FIELDS.map((field) => (
          <div key={field.key} className="flex flex-col gap-1">
            <label htmlFor={`watchlist-filter-${field.key}`} className="text-xs font-medium text-slate-500 dark:text-slate-400">
              {field.label}
            </label>
            <input
              id={`watchlist-filter-${field.key}`}
              type="text"
              placeholder={field.placeholder}
              value={localFilters[field.key]}
              onChange={(event) => {
                setLocalFilters((prev) => ({ ...prev, [field.key]: event.target.value }));
              }}
              className={`${INPUT_CLASS} w-40`}
            />
          </div>
        ))}
        {activeCount > 0 && (
          <button
            type="button"
            onClick={() => {
              const empty: WatchlistFilters = { name: "", sector: "", country: "", theme: "", ticker: "" };
              setLocalFilters(empty);
              clearFilters();
            }}
            className="rounded-md px-3 py-2 text-sm font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
          >
            Clear filters
          </button>
        )}
      </div>
    </div>
  );
}
