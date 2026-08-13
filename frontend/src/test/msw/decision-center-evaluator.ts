import type { Alert, AlertRule } from "@/types/alerts";
import type { RecommendationCandidate } from "@/types/portfolio";
import type { ConditionEvaluation, MarketDataSnapshot, SignalCondition, SignalDefinition, SignalResult } from "@/types/signals";
import type { InvestmentStrategy, RuleAlignment, StrategyEvaluationResult, StrategyMatch } from "@/types/strategy";

/** A minimal mock evaluator shared by the Strategy/Signals/Alerts MSW
 * handlers — real enough (all 9 operators) for meaningful frontend
 * tests, not a reimplementation of any real backend engine. */
function evaluateOperator(operator: string, actual: unknown, expected: unknown): boolean {
  if (actual === undefined || actual === null) return false;
  switch (operator) {
    case "EQUALS":
      return actual === expected;
    case "NOT_EQUALS":
      return actual !== expected;
    case "GREATER_THAN":
      return (actual as number) > (expected as number);
    case "GREATER_EQUAL":
      return (actual as number) >= (expected as number);
    case "LESS_THAN":
      return (actual as number) < (expected as number);
    case "LESS_EQUAL":
      return (actual as number) <= (expected as number);
    case "BETWEEN": {
      const [low, high] = expected as [number, number];
      return (actual as number) >= low && (actual as number) <= high;
    }
    case "IN":
      return (expected as unknown[]).includes(actual);
    case "NOT_IN":
      return !(expected as unknown[]).includes(actual);
    default:
      return false;
  }
}

function resolveSnapshotField(snapshot: MarketDataSnapshot, path: string): unknown {
  const [namespace, field] = path.split(".");
  const record = (snapshot as unknown as Record<string, Record<string, unknown> | null | undefined>)[namespace ?? ""];
  return record ? record[field ?? ""] : undefined;
}

function evaluateSignalCondition(condition: SignalCondition, snapshot: MarketDataSnapshot): ConditionEvaluation {
  const actual = resolveSnapshotField(snapshot, condition.field);
  const passed = condition.enabled ? evaluateOperator(condition.operator, actual, condition.value) : true;
  return { condition_id: condition.id, field: condition.field, operator: condition.operator, weight: condition.weight, passed, reason: passed ? null : "Condition not satisfied." };
}

export function evaluateSignalDefinition(definition: SignalDefinition, snapshot: MarketDataSnapshot): SignalResult {
  const evaluations = definition.conditions.map((condition) => evaluateSignalCondition(condition, snapshot));
  const matched = evaluations.filter((e) => e.passed);
  const failed = evaluations.filter((e) => !e.passed);
  const triggered = evaluations.length > 0 && failed.length === 0;
  return {
    ticker: snapshot.ticker,
    company_name: snapshot.company_name ?? null,
    signal_name: definition.name,
    category: definition.category,
    triggered,
    confidence: triggered ? 90 : 40,
    score: evaluations.length === 0 ? 0 : (matched.length / evaluations.length) * 100,
    priority: definition.priority,
    matched_conditions: matched,
    failed_conditions: failed,
    reason: triggered ? `${definition.name} triggered.` : `${definition.name} did not trigger.`,
    timestamp: new Date().toISOString(),
  };
}

export function evaluateStrategies(
  requestId: string,
  candidates: RecommendationCandidate[],
  strategies: InvestmentStrategy[],
): StrategyEvaluationResult {
  const matches: StrategyMatch[] = strategies.map((strategy) => {
    const ruleAlignments: RuleAlignment[] = strategy.rules.map((rule) => {
      const evaluable = candidates.filter((c) => (c as unknown as Record<string, unknown>)[rule.field] !== null && (c as unknown as Record<string, unknown>)[rule.field] !== undefined);
      const passing = evaluable.filter((c) => evaluateOperator(rule.operator, (c as unknown as Record<string, unknown>)[rule.field], rule.value));
      const passRate = evaluable.length === 0 ? 0 : passing.length / evaluable.length;
      return {
        rule_id: rule.id,
        field: rule.field,
        operator: rule.operator,
        weight: rule.weight,
        pass_rate: passRate,
        evaluated_candidate_count: evaluable.length,
        reason: `${String(passing.length)} of ${String(evaluable.length)} candidates satisfied this rule.`,
      };
    });
    const matched_rules = ruleAlignments.filter((r) => r.pass_rate >= 0.5);
    const failed_rules = ruleAlignments.filter((r) => r.pass_rate < 0.5);
    const alignment_score = ruleAlignments.length === 0 ? 50 : (ruleAlignments.reduce((sum, r) => sum + r.pass_rate, 0) / ruleAlignments.length) * 100;
    return {
      strategy_id: strategy.id,
      strategy_name: strategy.name,
      alignment_score,
      confidence: 80,
      matched_rules,
      failed_rules,
      reasoning: `${strategy.name} scored ${alignment_score.toFixed(0)} alignment across ${String(candidates.length)} candidates.`,
    };
  });

  const best = [...matches].sort((a, b) => b.alignment_score - a.alignment_score)[0];
  const alignments = matches.map((m) => m.alignment_score);

  return {
    request_id: requestId,
    evaluated_at: new Date().toISOString(),
    overall_alignment: alignments.length === 0 ? 0 : alignments.reduce((sum, v) => sum + v, 0) / alignments.length,
    best_strategy: best?.strategy_name ?? null,
    strategy_matches: matches,
    summary: {
      total_strategies: matches.length,
      best_alignment: best?.alignment_score ?? 0,
      average_alignment: alignments.length === 0 ? 0 : alignments.reduce((sum, v) => sum + v, 0) / alignments.length,
      highest_confidence: matches.length === 0 ? 0 : Math.max(...matches.map((m) => m.confidence)),
    },
  };
}

function evaluateAlertCondition(rule: AlertRule, signal: SignalResult): boolean {
  return rule.conditions.every((condition) => {
    if (!condition.enabled) return true;
    const actual = (signal as unknown as Record<string, unknown>)[condition.field];
    return evaluateOperator(condition.operator, actual, condition.value);
  });
}

export function evaluateAlerts(signals: SignalResult[], rules: AlertRule[], nextId: () => string): Alert[] {
  const alerts: Alert[] = [];
  for (const signal of signals) {
    for (const rule of rules) {
      if (!evaluateAlertCondition(rule, signal)) continue;
      alerts.push({
        id: nextId(),
        rule_id: rule.id,
        ticker: signal.ticker,
        company_name: signal.company_name,
        signal_name: signal.signal_name,
        alert_type: "SIGNAL_TRIGGERED",
        priority: rule.priority,
        status: "GENERATED",
        reason: `${signal.signal_name} matched rule "${rule.name}".`,
        confidence: signal.confidence,
        score: signal.score,
        eligible_channels: rule.channels,
        created_at: new Date().toISOString(),
      });
    }
  }
  return alerts;
}
