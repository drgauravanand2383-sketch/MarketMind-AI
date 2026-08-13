import type { ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useShowDataLabels } from "@/features/decision-center/charts/chart-preferences";
import type { RecommendationCandidate } from "@/types/portfolio";

const BUCKETS = [
  { label: "0-20", min: 0, max: 20 },
  { label: "20-40", min: 20, max: 40 },
  { label: "40-60", min: 40, max: 60 },
  { label: "60-80", min: 60, max: 80 },
  { label: "80-100", min: 80, max: 101 },
];

/** Buckets each candidate's already-computed `overall_score` into fixed
 * 20-point ranges for display — a presentation-only binning of real
 * backend scores, never a new score. */
export function RecommendationScoreDistributionChart({ candidates }: { candidates: RecommendationCandidate[] }): ReactNode {
  const showDataLabels = useShowDataLabels();
  const data = BUCKETS.map((bucket) => ({
    range: bucket.label,
    count: candidates.filter((c) => c.overall_score >= bucket.min && c.overall_score < bucket.max).length,
  }));

  return (
    <ResponsiveContainer width="100%" height={224}>
      <BarChart data={data} aria-label="Recommendation score distribution">
        <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
        <XAxis dataKey="range" tick={{ fontSize: 12 }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
        <Tooltip />
        <Bar dataKey="count" fill="#0ea5e9" radius={[4, 4, 0, 0]}>
          {showDataLabels && <LabelList dataKey="count" position="top" fontSize={11} />}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
