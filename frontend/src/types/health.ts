/**
 * Mirrors `app.operations.health.models` and `app.api.v1.schemas.system`
 * exactly (see `docs/architecture/API_ARCHITECTURE.md`).
 */

export type HealthState = "HEALTHY" | "DEGRADED" | "UNHEALTHY";

export interface ComponentHealth {
  name: string;
  state: HealthState;
  message: string;
}

export interface ApplicationHealth {
  state: HealthState;
  repositories: ComponentHealth[];
  services: ComponentHealth[];
  dependencies: ComponentHealth[];
  checked_at: string;
  summary: string;
}

export interface ReadinessStatus {
  ready: boolean;
  application_health: ApplicationHealth;
  blocking_issues: string[];
}

export interface VersionResponse {
  api_version: string;
  application_version: string;
  environment: string;
}
