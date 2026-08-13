import { useState, type ReactNode } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { FormField } from "@/components/forms/form-field";
import { LoadingButton } from "@/components/forms/loading-button";
import { SnapshotBuilder } from "@/features/historical-analysis/backtesting/snapshot-builder";
import { useCreateBacktest } from "@/hooks/use-backtesting";
import { useStrategiesList } from "@/hooks/use-strategy";
import { REPLAY_MODES } from "@/types/backtesting";
import type { HistoricalSnapshot } from "@/types/backtesting";

const createBacktestSchema = z
  .object({
    name: z.string().min(1, "Name is required"),
    description: z.string(),
    start_date: z.string().min(1, "Start date is required"),
    end_date: z.string().min(1, "End date is required"),
    initial_capital: z.coerce.number().gt(0, "Must be greater than 0"),
    benchmark: z.string().min(1, "Benchmark ticker is required"),
    replay_mode: z.enum(["DAILY", "WEEKLY", "MONTHLY", "CUSTOM"]),
  })
  .refine((values) => values.start_date <= values.end_date, {
    message: "Start date must not be after end date",
    path: ["end_date"],
  });

type CreateBacktestValues = z.infer<typeof createBacktestSchema>;

export function CreateBacktestForm(): ReactNode {
  const navigate = useNavigate();
  const createBacktest = useCreateBacktest();
  const strategies = useStrategiesList({ page: 1, page_size: 100, sort: "name", direction: "asc" });
  const [selectedStrategyIds, setSelectedStrategyIds] = useState<string[]>([]);
  const [snapshots, setSnapshots] = useState<HistoricalSnapshot[]>([]);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CreateBacktestValues>({
    resolver: zodResolver(createBacktestSchema),
    defaultValues: { name: "", description: "", start_date: "", end_date: "", initial_capital: 100000, benchmark: "SPY", replay_mode: "DAILY" },
  });

  function toggleStrategy(id: string): void {
    setSelectedStrategyIds((prev) => (prev.includes(id) ? prev.filter((existing) => existing !== id) : [...prev, id]));
  }

  const submit = handleSubmit((values: CreateBacktestValues) => {
    createBacktest.mutate(
      {
        name: values.name,
        description: values.description,
        start_date: values.start_date,
        end_date: values.end_date,
        initial_capital: values.initial_capital,
        benchmark: values.benchmark.toUpperCase(),
        replay_mode: values.replay_mode,
        strategy_ids: selectedStrategyIds,
        snapshots,
      },
      {
        onSuccess: (result) => {
          void navigate({ to: "/historical-analysis/backtests/$runId", params: { runId: result.request_id } });
        },
      },
    );
  });

  return (
    <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-5" noValidate aria-busy={createBacktest.isPending}>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormField label="Name" autoComplete="off" error={errors.name?.message} {...register("name")} />
        <FormField label="Description (optional)" autoComplete="off" {...register("description")} />
        <FormField label="Start date" type="date" error={errors.start_date?.message} {...register("start_date")} />
        <FormField label="End date" type="date" error={errors.end_date?.message} {...register("end_date")} />
        <FormField label="Initial capital" type="number" error={errors.initial_capital?.message} {...register("initial_capital")} />
        <FormField label="Benchmark ticker" placeholder="e.g. SPY" autoComplete="off" error={errors.benchmark?.message} {...register("benchmark")} />
        <div className="flex flex-col gap-1">
          <label htmlFor="replay_mode" className="text-sm font-medium text-slate-700 dark:text-slate-300">
            Replay mode
          </label>
          <select
            id="replay_mode"
            className="rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            {...register("replay_mode")}
          >
            {REPLAY_MODES.map((mode) => (
              <option key={mode} value={mode}>
                {mode}
              </option>
            ))}
          </select>
        </div>
      </div>

      <fieldset className="flex flex-col gap-1.5">
        <legend className="text-xs font-medium text-slate-500 dark:text-slate-400">Strategies to track (optional)</legend>
        {strategies.data?.data.map((strategy) => (
          <label key={strategy.id} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input type="checkbox" checked={selectedStrategyIds.includes(strategy.id)} onChange={() => { toggleStrategy(strategy.id); }} />
            {strategy.name}
          </label>
        ))}
      </fieldset>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-300">Historical snapshots</h3>
        <SnapshotBuilder onChange={setSnapshots} />
      </div>

      <div className="flex items-center gap-3">
        <LoadingButton isLoading={createBacktest.isPending} loadingText="Running…">
          Run backtest
        </LoadingButton>
        {createBacktest.isPending && (
          <p role="status" aria-live="polite" className="text-sm text-slate-500 dark:text-slate-400">
            Replaying {snapshots.length} {snapshots.length === 1 ? "snapshot" : "snapshots"}…
          </p>
        )}
      </div>
    </form>
  );
}
