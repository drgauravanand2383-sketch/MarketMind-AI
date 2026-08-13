import type { ReactNode } from "react";
import type { RecommendationSummary } from "@/types/portfolio";

function Card({ label, value }: { label: string; value: string }): ReactNode {
  return (
    <div className="rounded-lg border border-slate-200 p-3 text-center dark:border-slate-800">
      <p className="text-lg font-semibold text-slate-900 dark:text-slate-100">{value}</p>
      <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
    </div>
  );
}

export function RecommendationSummaryCards({ summary }: { summary: RecommendationSummary }): ReactNode {
  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-7">
      <Card label="Strong Buy" value={String(summary.strong_buy)} />
      <Card label="Buy" value={String(summary.buy)} />
      <Card label="Watch" value={String(summary.watch)} />
      <Card label="Hold" value={String(summary.hold)} />
      <Card label="Avoid" value={String(summary.avoid)} />
      <Card label="Avg score" value={summary.average_score.toFixed(0)} />
      {/* `confidence` is already on a 0-100 scale here (unlike Research's
          0-1 `overall_confidence`) — see `app/recommendations/engine.py`'s
          own `f"...confidence {confidence}%..."` formatting. */}
      <Card label="Avg confidence" value={`${summary.average_confidence.toFixed(0)}%`} />
    </div>
  );
}
