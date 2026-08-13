import type { BacktestPeriod, BacktestResult, BacktestRun, CreateBacktestRequest } from "@/types/backtesting";

/** A tiny in-memory stand-in for the Backtesting Framework's durable
 * repository (`BaseBacktestRepository`, `app/backtesting/engine.py`) —
 * unlike `result-store.ts`'s ephemeral `InMemoryResultStore` mirror, a
 * run created here stays gettable for the rest of the test (matching
 * the real backend's durable persistence, see `types/backtesting.ts`'s
 * own module docstring). */

interface StoredBacktest {
  run: BacktestRun;
  result: BacktestResult;
}

const backtestsByRunId = new Map<string, StoredBacktest>();
let nextId = 1;

export function resetBacktestingStore(): void {
  backtestsByRunId.clear();
  nextId = 1;
}

/** Deterministically derives one `BacktestPeriod` per submitted snapshot
 * — a mock stand-in for `app/backtesting/engine.py`'s own replay logic,
 * not a reimplementation of it. Zero snapshots yields zero periods,
 * matching the real backend's documented behavior. */
function buildPeriods(snapshots: CreateBacktestRequest["snapshots"]): BacktestPeriod[] {
  return (snapshots ?? []).map((snapshot, index) => {
    const returnPercent = 4 - index * 3;
    return {
      timestamp: snapshot.timestamp,
      portfolio_value: 100_000 * (1 + returnPercent / 100),
      benchmark_value: snapshot.benchmark_value ?? 100_000 * (1 + (returnPercent - 1) / 100),
      return_percent: returnPercent,
      notes: `Period ${String(index + 1)}`,
    };
  });
}

export function createBacktest(body: CreateBacktestRequest): BacktestResult {
  const runId = `test-backtest-${String(nextId)}`;
  nextId += 1;

  const periods = buildPeriods(body.snapshots);
  const totalPeriods = periods.length;
  const successfulPeriods = periods.filter((period) => period.return_percent >= 0).length;
  const portfolioReturn = totalPeriods > 0 ? periods[totalPeriods - 1]!.return_percent : 0;
  const benchmarkReturn = portfolioReturn - 1;
  const generatedAt = "2026-02-01T00:05:00Z";

  const run: BacktestRun = {
    request_id: runId,
    started_at: "2026-02-01T00:00:00Z",
    completed_at: generatedAt,
    status: "COMPLETED",
    processed_snapshots: (body.snapshots ?? []).length,
    results: periods,
  };

  const result: BacktestResult = {
    request_id: runId,
    portfolio_return: portfolioReturn,
    benchmark_return: benchmarkReturn,
    excess_return: portfolioReturn - benchmarkReturn,
    max_drawdown: totalPeriods > 0 ? 3.2 : 0,
    win_rate: totalPeriods > 0 ? (successfulPeriods / totalPeriods) * 100 : 0,
    total_periods: totalPeriods,
    successful_periods: successfulPeriods,
    failed_periods: totalPeriods - successfulPeriods,
    summary: `Backtest "${body.name}" completed with ${String(totalPeriods)} periods.`,
    generated_at: generatedAt,
  };

  backtestsByRunId.set(runId, { run, result });
  return result;
}

/** Lets a test seed an exact `BacktestRun`/`BacktestResult` pair directly
 * (bypassing `POST /backtests`) — used by detail-page/comparison tests
 * that want to assert against known, hand-picked values rather than the
 * generic derivation `createBacktest` produces. */
export function seedBacktest(run: BacktestRun, result: BacktestResult): void {
  backtestsByRunId.set(run.request_id, { run, result });
}

export function getBacktestRun(runId: string): BacktestRun | undefined {
  return backtestsByRunId.get(runId)?.run;
}

export function getBacktestResult(runId: string): BacktestResult | undefined {
  return backtestsByRunId.get(runId)?.result;
}
