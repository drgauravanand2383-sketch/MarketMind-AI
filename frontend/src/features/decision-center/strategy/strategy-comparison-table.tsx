import { useMemo, type ReactNode } from "react";
import type { StrategyEvaluationResult, StrategyMatch } from "@/types/strategy";

/** `strategy_matches` arrives already ranked/scored server-side — no
 * client-side computation beyond a display sort by `alignment_score`
 * (already the array's natural order in practice, but sorting explicitly
 * keeps the table correct even if that ever weren't true). */
export function StrategyComparisonTable({
  result,
  selectedStrategyId,
  onSelect,
}: {
  result: StrategyEvaluationResult;
  selectedStrategyId: string | null;
  onSelect: (strategyId: string) => void;
}): ReactNode {
  const ranked: StrategyMatch[] = useMemo(
    () => [...result.strategy_matches].sort((a, b) => b.alignment_score - a.alignment_score),
    [result.strategy_matches],
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Strategy comparison</caption>
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800">
            <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
              Strategy
            </th>
            <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
              Alignment
            </th>
            <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
              Confidence
            </th>
          </tr>
        </thead>
        <tbody>
          {ranked.map((match) => {
            const isBest = match.strategy_name === result.best_strategy;
            return (
              <tr
                key={match.strategy_id}
                aria-selected={selectedStrategyId === match.strategy_id}
                className={`border-b border-slate-100 dark:border-slate-800/60 ${
                  selectedStrategyId === match.strategy_id ? "bg-brand-50 dark:bg-brand-500/10" : ""
                }`}
              >
                <td className="px-3 py-2">
                  <button
                    type="button"
                    onClick={() => {
                      onSelect(match.strategy_id);
                    }}
                    className="font-medium text-brand-700 hover:underline dark:text-brand-400"
                  >
                    {match.strategy_name}
                  </button>
                  {isBest && (
                    <span className="ml-2 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-500/10 dark:text-green-400">
                      Best match
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{match.alignment_score.toFixed(0)}</td>
                <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{match.confidence.toFixed(0)}%</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
