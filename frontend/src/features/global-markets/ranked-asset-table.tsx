import { useMemo, useState, type ReactNode } from "react";
import { Badge } from "@/components/badge";
import type { RankedAsset, RiskClassification } from "@/types/global-markets";

type SortField = "rank" | "ticker" | "final_score";

/** Never implies fraud/manipulation — same terminology discipline
 * `RiskClassification`'s own backend docstring requires, just rendered
 * as a readable label instead of the raw enum member. */
const RISK_LABELS: Record<RiskClassification, string> = {
  STRONG_MOMENTUM_LOWER_RISK: "Strong momentum, lower risk",
  STRONG_MOMENTUM_MODERATE_RISK: "Strong momentum, moderate risk",
  STRONG_MOMENTUM_HIGH_RISK: "Strong momentum, high risk",
  EXTREME_MOMENTUM_EXTREME_RISK: "Extreme momentum, extreme risk",
  MODERATE_MOMENTUM: "Moderate momentum",
  WEAK_MOMENTUM: "Weak momentum",
  INSUFFICIENT_CONFIDENCE: "Insufficient data confidence",
};

function formatPrice(price: number | null, currency: string | null): string {
  if (price === null) return "—";
  return currency ? `${currency} ${price.toLocaleString(undefined, { maximumFractionDigits: 4 })}` : price.toLocaleString();
}

function formatMarketCap(marketCap: number | null): string {
  if (marketCap === null) return "—";
  if (marketCap >= 1e12) return `${(marketCap / 1e12).toFixed(2)}T`;
  if (marketCap >= 1e9) return `${(marketCap / 1e9).toFixed(2)}B`;
  if (marketCap >= 1e6) return `${(marketCap / 1e6).toFixed(2)}M`;
  return marketCap.toLocaleString();
}

/**
 * The Top-N (15 main categories, 20 penny/micro-cap) ranked-asset list
 * for one report category — fixed-size and returned unpaginated by
 * `GET .../ranked-assets` (page_size 100 always covers it, see
 * `services/api/global-markets-api.ts`), so — like
 * `ScreeningResultsTable`'s own documented exception — sorting here is a
 * deliberate frontend computation with no server-side equivalent to
 * defer to, but pagination itself is never needed.
 */
export function RankedAssetTable({ assets }: { assets: RankedAsset[] }): ReactNode {
  const [sortField, setSortField] = useState<SortField>("rank");
  const [sortDesc, setSortDesc] = useState(false);

  const showRiskColumn = assets.some((asset) => asset.risk_classification !== null);

  const sorted = useMemo(() => {
    const copy = [...assets];
    copy.sort((a, b) => {
      const comparison =
        sortField === "rank"
          ? a.rank - b.rank
          : sortField === "final_score"
            ? a.final_score - b.final_score
            : a.snapshot.ticker.localeCompare(b.snapshot.ticker);
      return sortDesc ? -comparison : comparison;
    });
    return copy;
  }, [assets, sortField, sortDesc]);

  function toggleSort(field: SortField): void {
    if (field === sortField) {
      setSortDesc((prev) => !prev);
    } else {
      setSortField(field);
      setSortDesc(field !== "rank");
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Ranked assets</caption>
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800">
            <SortHeader label="Rank" field="rank" active={sortField} desc={sortDesc} onSort={toggleSort} />
            <SortHeader label="Ticker" field="ticker" active={sortField} desc={sortDesc} onSort={toggleSort} />
            <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
              Price
            </th>
            <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
              Market cap
            </th>
            <SortHeader label="Score" field="final_score" active={sortField} desc={sortDesc} onSort={toggleSort} />
            {showRiskColumn && (
              <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
                Risk classification
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {sorted.map((asset) => (
            <tr key={asset.snapshot.ticker} className="border-b border-slate-100 align-top dark:border-slate-800/60">
              <td className="px-3 py-2 text-slate-500 dark:text-slate-400">{asset.rank}</td>
              <td className="px-3 py-2">
                <div className="font-medium text-slate-800 dark:text-slate-200">{asset.snapshot.ticker}</div>
                {asset.snapshot.name && <div className="text-xs text-slate-500 dark:text-slate-400">{asset.snapshot.name}</div>}
              </td>
              <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{formatPrice(asset.snapshot.price, asset.snapshot.currency)}</td>
              <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{formatMarketCap(asset.snapshot.market_cap)}</td>
              <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{asset.final_score.toFixed(1)}</td>
              {showRiskColumn && (
                <td className="px-3 py-2">
                  {asset.risk_classification ? <Badge label={RISK_LABELS[asset.risk_classification]} /> : "—"}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
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
