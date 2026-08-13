import type { ReactNode } from "react";
import type { RecommendationType } from "@/types/portfolio";

const TYPE_STYLES: Record<RecommendationType, string> = {
  STRONG_BUY: "bg-green-100 text-green-800 dark:bg-green-500/10 dark:text-green-400",
  BUY: "bg-teal-100 text-teal-800 dark:bg-teal-500/10 dark:text-teal-400",
  WATCH: "bg-blue-100 text-blue-800 dark:bg-blue-500/10 dark:text-blue-400",
  HOLD: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  AVOID: "bg-red-100 text-red-800 dark:bg-red-500/10 dark:text-red-400",
};

const TYPE_LABELS: Record<RecommendationType, string> = {
  STRONG_BUY: "Strong Buy",
  BUY: "Buy",
  WATCH: "Watch",
  HOLD: "Hold",
  AVOID: "Avoid",
};

export function RecommendationTypeBadge({ type }: { type: RecommendationType }): ReactNode {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${TYPE_STYLES[type]}`}>{TYPE_LABELS[type]}</span>;
}
