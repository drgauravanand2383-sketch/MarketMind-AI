import type { Alert, AlertRule } from "@/types/alerts";
import type { SignalDefinition } from "@/types/signals";
import type { InvestmentStrategy } from "@/types/strategy";

/** Stateful in-memory stand-ins for the Strategy/Signals/Alerts domains'
 * list-backed data — mirrors `test/msw/watchlist-store.ts`'s role.
 * `alertRules` has no corresponding REST endpoint on the real backend at
 * all (confirmed — no rule-CRUD, no rule-listing) so it exists here only
 * for the mock alert-evaluation logic in `decision-center-evaluator.ts`
 * to read; the frontend itself never sees this list directly. */

let strategies: InvestmentStrategy[] = [];
let signalDefinitions: SignalDefinition[] = [];
let alertRules: AlertRule[] = [];
let alerts: Alert[] = [];
let nextAlertId = 1;

export function resetDecisionCenterStore(
  seed: { strategies?: InvestmentStrategy[]; signalDefinitions?: SignalDefinition[]; alertRules?: AlertRule[]; alerts?: Alert[] } = {},
): void {
  strategies = seed.strategies ?? [];
  signalDefinitions = seed.signalDefinitions ?? [];
  alertRules = seed.alertRules ?? [];
  alerts = seed.alerts ?? [];
  nextAlertId = 1;
}

export function listStrategies(): InvestmentStrategy[] {
  return strategies;
}

export function getStrategy(id: string): InvestmentStrategy | undefined {
  return strategies.find((strategy) => strategy.id === id);
}

export function listSignalDefinitions(): SignalDefinition[] {
  return signalDefinitions;
}

export function getSignalDefinition(id: string): SignalDefinition | undefined {
  return signalDefinitions.find((definition) => definition.id === id);
}

export function listEnabledAlertRules(): AlertRule[] {
  return alertRules.filter((rule) => rule.enabled);
}

export function listAlerts(): Alert[] {
  return alerts;
}

export function appendAlerts(newAlerts: Alert[]): void {
  alerts = [...newAlerts, ...alerts];
}

export function nextAlertIdValue(): string {
  const id = `test-alert-${String(nextAlertId)}`;
  nextAlertId += 1;
  return id;
}
