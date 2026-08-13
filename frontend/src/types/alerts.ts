import type { SignalResult } from "@/types/signals";

/**
 * Mirrors `app.alerts.models` field-for-field (verified against the
 * actual backend source, Frontend Milestone 5). There is **no REST
 * endpoint anywhere to list, create, or otherwise discover `AlertRule`s**
 * — `POST /alerts/evaluate`'s `rule_ids` can only ever reference rules
 * the caller already knows the id of by some other means. This frontend
 * therefore always evaluates with `rule_ids: []` ("every enabled rule")
 * — there is no rule-picker UI, because there is nothing for one to list.
 *
 * `Alert` has **no field linking it back to a `Recommendation`** — only
 * `rule_id`/`ticker`/`signal_name`. Any "related recommendation" shown in
 * this milestone's UI is a client-side ticker match against whatever
 * `RecommendationCandidate`s are currently loaded, explicitly labeled as
 * inferred, never a backend-asserted relationship (see
 * `docs/frontend/MILESTONE_5.md`).
 */

export type NotificationChannel = "EMAIL" | "PUSH" | "SMS" | "TELEGRAM" | "DISCORD" | "SLACK" | "WEBHOOK" | "IN_APP";

export type AlertStatus = "PENDING" | "GENERATED" | "SUPPRESSED" | "DISMISSED" | "EXPIRED";

export type AlertPriority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface AlertCondition {
  id: string;
  /** One of `SignalResult`'s own scalar field names — never
   * `matched_conditions`/`failed_conditions`. */
  field: string;
  operator: "EQUALS" | "NOT_EQUALS" | "GREATER_THAN" | "GREATER_EQUAL" | "LESS_THAN" | "LESS_EQUAL" | "BETWEEN" | "IN" | "NOT_IN";
  value: unknown;
  enabled: boolean;
}

export interface AlertRule {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  priority: AlertPriority;
  conditions: AlertCondition[];
  cooldown_minutes: number;
  repeat_allowed: boolean;
  channels: NotificationChannel[];
  created_at: string;
  updated_at: string;
}

export interface Alert {
  id: string;
  rule_id: string;
  ticker: string;
  company_name: string | null;
  signal_name: string;
  alert_type: string;
  priority: AlertPriority;
  status: AlertStatus;
  reason: string;
  confidence: number;
  score: number;
  eligible_channels: NotificationChannel[];
  created_at: string;
}

export interface AlertBatch {
  alerts: Alert[];
  generated: number;
  suppressed: number;
  summary: string;
}

export interface EvaluateAlertsRequest {
  signals: SignalResult[];
  /** Always sent empty by this frontend — see module docstring. */
  rule_ids?: string[];
}

export interface ListAlertsParams {
  page?: number;
  page_size?: number;
  sort?: "created_at" | "priority" | "status" | "ticker";
  direction?: "asc" | "desc";
  [key: string]: string | number | undefined;
}
