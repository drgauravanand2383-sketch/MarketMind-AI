import { useMemo, useState, type ReactNode } from "react";
import { Badge } from "@/components/badge";
import { EmptyState } from "@/components/states/empty-state";
import { Pagination } from "@/components/table/pagination";
import type { ScreenResult } from "@/types/screening";

type PassFilter = "all" | "passed" | "failed";
type SortField = "ticker" | "company_name" | "score";

const PAGE_SIZE = 20;

/**
 * `POST /screening/run` / `GET /screening/results/{id}` return the full,
 * unpaginated `ScreenResult[]` in one call — no server-side page/sort/
 * filter params exist for it (unlike watchlists/screening-profiles,
 * where a server equivalent exists and must be used instead). Sorting,
 * filtering, and pagination here are therefore a deliberate, reasoned
 * exception to "no frontend computation," since there is no server
 * alternative to defer to.
 */
export function ScreeningResultsTable({ results }: { results: ScreenResult[] }): ReactNode {
  const [passFilter, setPassFilter] = useState<PassFilter>("all");
  const [search, setSearch] = useState("");
  const [sortField, setSortField] = useState<SortField>("score");
  const [sortDesc, setSortDesc] = useState(true);
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return results.filter((result) => {
      if (passFilter === "passed" && !result.passed) return false;
      if (passFilter === "failed" && result.passed) return false;
      if (needle && !result.ticker.toLowerCase().includes(needle) && !(result.company_name ?? "").toLowerCase().includes(needle)) {
        return false;
      }
      return true;
    });
  }, [results, passFilter, search]);

  const sorted = useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => {
      const comparison =
        sortField === "score"
          ? a.score - b.score
          : sortField === "ticker"
            ? a.ticker.localeCompare(b.ticker)
            : (a.company_name ?? "").localeCompare(b.company_name ?? "");
      return sortDesc ? -comparison : comparison;
    });
    return copy;
  }, [filtered, sortField, sortDesc]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const pageItems = sorted.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  function toggleSort(field: SortField): void {
    if (field === sortField) {
      setSortDesc((prev) => !prev);
    } else {
      setSortField(field);
      setSortDesc(true);
    }
    setPage(1);
  }

  const matchedCount = results.filter((r) => r.passed).length;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-sm text-slate-600 dark:text-slate-300">
          {matchedCount} of {results.length} companies matched
        </p>
        <label htmlFor="screening-results-search" className="sr-only">
          Search results by ticker or company name
        </label>
        <input
          id="screening-results-search"
          type="search"
          data-shortcut-target="search"
          placeholder="Search ticker or company…"
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        <div role="group" aria-label="Filter by match status" className="flex gap-1">
          {(["all", "passed", "failed"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={passFilter === option}
              onClick={() => {
                setPassFilter(option);
                setPage(1);
              }}
              className={
                passFilter === option
                  ? "rounded-md bg-brand-600 px-3 py-1.5 text-xs font-medium text-white"
                  : "rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              }
            >
              {option === "all" ? "All" : option === "passed" ? "Matched" : "Not matched"}
            </button>
          ))}
        </div>
      </div>

      {sorted.length === 0 ? (
        <EmptyState title="No companies match this filter" description="Try clearing the search or match-status filter." />
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Screening results</caption>
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800">
                  <SortHeader label="Ticker" field="ticker" active={sortField} desc={sortDesc} onSort={toggleSort} />
                  <SortHeader label="Company" field="company_name" active={sortField} desc={sortDesc} onSort={toggleSort} />
                  <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                    Status
                  </th>
                  <SortHeader label="Score" field="score" active={sortField} desc={sortDesc} onSort={toggleSort} />
                  <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                    Matched filters
                  </th>
                  <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                    Failed filters
                  </th>
                </tr>
              </thead>
              <tbody>
                {pageItems.map((result) => (
                  <tr key={result.ticker} className="border-b border-slate-100 align-top dark:border-slate-800/60">
                    <td className="px-3 py-2 font-medium text-slate-800 dark:text-slate-200">{result.ticker}</td>
                    <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{result.company_name ?? "—"}</td>
                    <td className="px-3 py-2">
                      <Badge label={result.passed ? "Matched" : "Not matched"} tone={result.passed ? "auto" : "neutral"} />
                    </td>
                    <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{result.score.toFixed(1)}</td>
                    <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">
                      {result.matched_filters.length === 0 ? "—" : result.matched_filters.map((f) => f.field).join(", ")}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">
                      {result.failed_filters.length === 0
                        ? "—"
                        : result.failed_filters.map((f) => `${f.field}${f.reason ? ` (${f.reason})` : ""}`).join(", ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={currentPage} pageSize={PAGE_SIZE} total={sorted.length} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}

function SortHeader({
  label,
  field,
  active,
  desc,
  onSort,
}: {
  label: string;
  field: SortField;
  active: SortField;
  desc: boolean;
  onSort: (field: SortField) => void;
}): ReactNode {
  const isActive = field === active;
  return (
    <th scope="col" aria-sort={isActive ? (desc ? "descending" : "ascending") : "none"} className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
      <button
        type="button"
        onClick={() => {
          onSort(field);
        }}
        className="flex items-center gap-1 hover:text-slate-900 dark:hover:text-slate-100"
      >
        {label}
        {isActive && <span aria-hidden="true">{desc ? "▼" : "▲"}</span>}
      </button>
    </th>
  );
}
