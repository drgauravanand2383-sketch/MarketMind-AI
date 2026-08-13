import type { CompanyMetrics, FilterEvaluation, ScreenFilter, ScreenResult, ScreeningProfile } from "@/types/screening";

/** A minimal mock evaluator for MSW's `POST /screening/run` handler —
 * mirrors `ScreeningEngine.evaluate_companies()`'s per-filter semantics
 * closely enough for meaningful frontend tests (all 9 `ScreenOperator`s,
 * enabled/disabled, matched/failed split), but is not a reimplementation
 * of the real engine — groups/AND-OR nesting collapse to "every enabled
 * top-level filter must pass," which is sufficient for this frontend's
 * own test coverage. */
function evaluateFilter(filter: ScreenFilter, metrics: CompanyMetrics): FilterEvaluation {
  const actual = (metrics as unknown as Record<string, unknown>)[filter.field];
  const base = { filter_id: filter.id, field: filter.field, operator: filter.operator };

  if (!filter.enabled) {
    return { ...base, passed: true, reason: null };
  }
  if (actual === undefined || actual === null) {
    return { ...base, passed: false, reason: "Metric not supplied." };
  }

  switch (filter.operator) {
    case "EQUALS":
      return { ...base, passed: actual === filter.value, reason: actual === filter.value ? null : "Value did not match." };
    case "NOT_EQUALS":
      return { ...base, passed: actual !== filter.value, reason: actual !== filter.value ? null : "Value matched (expected not to)." };
    case "GREATER_THAN":
      return { ...base, passed: (actual as number) > (filter.value as number), reason: (actual as number) > (filter.value as number) ? null : "Value not greater than threshold." };
    case "GREATER_EQUAL":
      return { ...base, passed: (actual as number) >= (filter.value as number), reason: (actual as number) >= (filter.value as number) ? null : "Value below threshold." };
    case "LESS_THAN":
      return { ...base, passed: (actual as number) < (filter.value as number), reason: (actual as number) < (filter.value as number) ? null : "Value not less than threshold." };
    case "LESS_EQUAL":
      return { ...base, passed: (actual as number) <= (filter.value as number), reason: (actual as number) <= (filter.value as number) ? null : "Value above threshold." };
    case "BETWEEN": {
      const [low, high] = filter.value as [number, number];
      const passed = (actual as number) >= low && (actual as number) <= high;
      return { ...base, passed, reason: passed ? null : "Value outside range." };
    }
    case "IN": {
      const passed = (filter.value as unknown[]).includes(actual);
      return { ...base, passed, reason: passed ? null : "Value not in allowed set." };
    }
    case "NOT_IN": {
      const passed = !(filter.value as unknown[]).includes(actual);
      return { ...base, passed, reason: passed ? null : "Value in excluded set." };
    }
    default:
      return { ...base, passed: false, reason: "Unknown operator." };
  }
}

export function evaluateCompany(profile: ScreeningProfile, metrics: CompanyMetrics): ScreenResult {
  const evaluations = profile.filters.map((filter) => evaluateFilter(filter, metrics));
  const matched_filters = evaluations.filter((e) => e.passed);
  const failed_filters = evaluations.filter((e) => !e.passed);
  const enabledCount = profile.filters.filter((f) => f.enabled).length;
  return {
    ticker: metrics.ticker,
    company_name: metrics.company_name,
    passed: failed_filters.length === 0,
    matched_filters,
    failed_filters,
    score: evaluations.length === 0 ? 100 : (matched_filters.length / evaluations.length) * 100,
    details: { total_filters: profile.filters.length, enabled_filters: enabledCount, disabled_filters: profile.filters.length - enabledCount },
  };
}
