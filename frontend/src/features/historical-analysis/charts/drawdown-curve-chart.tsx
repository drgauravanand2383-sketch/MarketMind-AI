import type { ReactNode } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { EmptyState } from "@/components/states/empty-state";
import type { BacktestPeriod } from "@/types/backtesting";

function formatTick(value: string): string {
  return new Date(value).toLocaleDateString();
}

/**
 * The backend only returns one summary number, `BacktestResult
 * .max_drawdown` — the single worst peak-to-trough decline across the
 * whole run, never a per-period series. A "drawdown curve" needs a
 * value at every point in time, so this derives one by running the
 * exact same peak-to-trough formula `app/backtesting/engine.py` itself
 * uses for `max_drawdown` (L399-409) against each period's own
 * `portfolio_value` — a presentational chart-shape derivation from
 * already-returned values, not a new metric invented client-side; the
 * curve's own maximum will always equal the backend's `max_drawdown`.
 */
export function DrawdownCurveChart({ periods }: { periods: BacktestPeriod[] }): ReactNode {
  if (periods.length === 0) {
    return <EmptyState title="No periods to plot" description="This backtest has no periods — nothing to derive a drawdown curve from." />;
  }

  const { rows: data } = periods.reduce<{ peak: number; rows: { timestamp: string; drawdown: number }[] }>(
    (acc, period) => {
      const peak = Math.max(acc.peak, period.portfolio_value);
      const drawdown = peak > 0 ? ((peak - period.portfolio_value) / peak) * 100 : 0;
      return { peak, rows: [...acc.rows, { timestamp: period.timestamp, drawdown }] };
    },
    { peak: periods[0]?.portfolio_value ?? 0, rows: [] },
  );

  return (
    <ResponsiveContainer width="100%" height={224}>
      <AreaChart data={data} aria-label="Drawdown curve">
        <CartesianGrid strokeDasharray="3 3" className="stroke-slate-200 dark:stroke-slate-800" />
        <XAxis dataKey="timestamp" tickFormatter={formatTick} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 12 }} reversed />
        <Tooltip
          labelFormatter={(value) => (typeof value === "string" || typeof value === "number" ? new Date(value).toLocaleString() : "")}
          formatter={(value) => `${Number(value).toFixed(2)}%`}
        />
        <Area type="monotone" dataKey="drawdown" stroke="#ef4444" fill="#fecaca" fillOpacity={0.5} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
