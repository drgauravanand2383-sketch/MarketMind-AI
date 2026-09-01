import type { CategoryIntelligenceReport, IntelligenceRun, RankedAsset, ReportCategory } from "@/types/global-markets";

/** A tiny in-memory stand-in for the Global Markets read-only repositories
 * — lets MSW-backed tests seed a run plus its per-category ranked assets
 * and narrative reports, mirroring the real `/api/v1/global-markets/*`
 * contract without reimplementing the backend. */

let runs: IntelligenceRun[] = [];
const rankedAssetsByRunAndCategory = new Map<string, RankedAsset[]>();
const reportsByRunAndCategory = new Map<string, CategoryIntelligenceReport>();

function key(runId: string, category: ReportCategory): string {
  return `${runId}::${category}`;
}

export function resetGlobalMarketsStore(): void {
  runs = [];
  rankedAssetsByRunAndCategory.clear();
  reportsByRunAndCategory.clear();
}

export function seedRun(run: IntelligenceRun): void {
  runs = [run, ...runs.filter((existing) => existing.id !== run.id)];
}

export function seedRankedAssets(runId: string, category: ReportCategory, assets: RankedAsset[]): void {
  rankedAssetsByRunAndCategory.set(key(runId, category), assets);
}

export function seedReport(report: CategoryIntelligenceReport): void {
  reportsByRunAndCategory.set(key(report.run_id, report.category), report);
}

export function getLatestRun(): IntelligenceRun | undefined {
  return runs[0];
}

/** Most-recent-first, matching `seedRun`'s own unshift-to-front
 * ordering — the same order the real `/global-markets/runs` endpoint
 * returns (sorted by `run_date` descending). */
export function listRuns(): IntelligenceRun[] {
  return runs;
}

export function getRun(runId: string): IntelligenceRun | undefined {
  return runs.find((run) => run.id === runId);
}

export function getRankedAssets(runId: string, category: ReportCategory): RankedAsset[] {
  return rankedAssetsByRunAndCategory.get(key(runId, category)) ?? [];
}

export function getReport(runId: string, category: ReportCategory): CategoryIntelligenceReport | undefined {
  return reportsByRunAndCategory.get(key(runId, category));
}
