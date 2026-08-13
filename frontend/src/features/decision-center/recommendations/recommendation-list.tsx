import { useMemo, useState, type ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";
import { RecommendationTypeBadge } from "@/features/decision-center/recommendations/recommendation-type-badge";
import type { RecommendationCandidate, RecommendationType } from "@/types/portfolio";

type SortField = "overall_score" | "confidence" | "ticker";
type TypeFilter = "ALL" | RecommendationType;

const TYPE_OPTIONS: TypeFilter[] = ["ALL", "STRONG_BUY", "BUY", "WATCH", "HOLD", "AVOID"];

/**
 * `RecommendationResult` returns every candidate in one unpaginated
 * array (no `GET /portfolio/recommendations/{id}` and no server-side
 * page/sort/filter params for it) — sort, filter, and search are the
 * same deliberate, reasoned client-side exception Milestone 4
 * established for screening results, since there's no server
 * alternative to defer to.
 */
export function RecommendationList({
  candidates,
  selectedTicker,
  onSelect,
}: {
  candidates: RecommendationCandidate[];
  selectedTicker: string | null;
  onSelect: (ticker: string) => void;
}): ReactNode {
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("ALL");
  const [sortField, setSortField] = useState<SortField>("overall_score");
  const [sortDesc, setSortDesc] = useState(true);

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return candidates.filter((candidate) => {
      if (typeFilter !== "ALL" && candidate.recommendation !== typeFilter) return false;
      if (needle && !candidate.ticker.toLowerCase().includes(needle) && !(candidate.company_name ?? "").toLowerCase().includes(needle)) {
        return false;
      }
      return true;
    });
  }, [candidates, search, typeFilter]);

  const sorted = useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => {
      const comparison =
        sortField === "ticker" ? a.ticker.localeCompare(b.ticker) : a[sortField] - b[sortField];
      return sortDesc ? -comparison : comparison;
    });
    return copy;
  }, [filtered, sortField, sortDesc]);

  function toggleSort(field: SortField): void {
    if (field === sortField) setSortDesc((prev) => !prev);
    else {
      setSortField(field);
      setSortDesc(true);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="recommendation-search" className="sr-only">
          Search recommendations by ticker or company name
        </label>
        <input
          id="recommendation-search"
          type="search"
          data-shortcut-target="search"
          placeholder="Search ticker or company…"
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
          }}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        />
        <label htmlFor="recommendation-type-filter" className="sr-only">
          Filter by recommendation type
        </label>
        <select
          id="recommendation-type-filter"
          value={typeFilter}
          onChange={(event) => {
            setTypeFilter(event.target.value as TypeFilter);
          }}
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        >
          {TYPE_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {option === "ALL" ? "All types" : option}
            </option>
          ))}
        </select>
      </div>

      {sorted.length === 0 ? (
        <EmptyState title="No candidates match" description="Try clearing the search or type filter." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Recommendation candidates</caption>
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800">
                <SortHeader label="Ticker" field="ticker" active={sortField} desc={sortDesc} onSort={toggleSort} />
                <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Company
                </th>
                <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Type
                </th>
                <SortHeader label="Score" field="overall_score" active={sortField} desc={sortDesc} onSort={toggleSort} />
                <SortHeader label="Confidence" field="confidence" active={sortField} desc={sortDesc} onSort={toggleSort} />
              </tr>
            </thead>
            <tbody>
              {sorted.map((candidate) => (
                <tr
                  key={candidate.ticker}
                  aria-selected={selectedTicker === candidate.ticker}
                  className={`cursor-pointer border-b border-slate-100 hover:bg-slate-50 dark:border-slate-800/60 dark:hover:bg-slate-800/40 ${
                    selectedTicker === candidate.ticker ? "bg-brand-50 dark:bg-brand-500/10" : ""
                  }`}
                >
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() => {
                        onSelect(candidate.ticker);
                      }}
                      className="font-medium text-brand-700 hover:underline dark:text-brand-400"
                    >
                      {candidate.ticker}
                    </button>
                  </td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{candidate.company_name ?? "—"}</td>
                  <td className="px-3 py-2">
                    <RecommendationTypeBadge type={candidate.recommendation} />
                  </td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{candidate.overall_score.toFixed(0)}</td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{candidate.confidence.toFixed(0)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
