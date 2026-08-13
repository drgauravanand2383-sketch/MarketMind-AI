# MarketMind AI Backend — Release Checklist

Produced by Sprint 54 (Production Hardening & Release Readiness), the
final planned backend sprint. Work through this checklist before every
production deployment. See `docs/architecture/BACKEND_ARCHITECTURE.md`
for the full architecture reference and `docs/database/MIGRATIONS.md` for
migration detail.

## 1. Database Migrations

- [ ] `DATABASE_URL` (or the individual `POSTGRES_*` variables) point at
      the target environment's real PostgreSQL server.
- [ ] `cd backend && alembic upgrade head` completes without error.
- [ ] `alembic current` reports `0001_baseline_schema (head)` (or the
      latest revision, if new migrations have been added since).
- [ ] Every table `app.operations.migrations.discovery.collect_table_names()`
      lists exists in the target database.

## 2. Configuration Validation

Run `ConfigurationValidationService.validate(...)` against the target
environment's real settings (already wired automatically inside
`bootstrap_application_state()` — inspect `app.state.startup_validation_report`,
or call it directly for a pre-deploy check) and confirm:

- [ ] No `ERROR`-severity check failed (`ANTHROPIC_API_KEY` present;
      every configured URL — RSS feed URLs, `DATABASE_URL` if set —
      well-formed; `postgres.port`/`api.port` valid).
- [ ] Review every `WARNING` (insecure default secret still in place,
      duplicate RSS feed URLs, an unrecognized `environment` or
      `llm.provider` value) — advisory, but each one should be a
      deliberate choice for this deployment, not an oversight.
- [ ] `POSTGRES_PASSWORD` (and any other secret) is not left at its
      insecure development default (`change-me`).

## 3. Dependency Validation

- [ ] `bootstrap_application_state()` runs to completion without raising
      (it is designed to degrade, not crash — but a `None` repository/
      service where one is expected for this deployment is a real gap).
- [ ] `app.state.startup_validation_report.passed` is `True` — inspect
      failed checks under `registered:*` (a required component failed to
      construct), `duplicate_registration:*`, and
      `model_metadata_discovery`/`model_metadata_uniqueness`.
- [ ] Every optional integration this deployment actually needs
      (ChromaDB, a real embedding provider, Redis) is genuinely reachable
      — these degrade to `None`/unused silently by design; confirm the
      degradation is expected, not accidental, for this environment.

## 4. Bootstrap Validation

- [ ] `HealthCheckService.check_readiness(...)` reports `ready=True`
      against the deployed repositories/services (every repository's own
      `health_check()` reaches the real database; every required service
      constructed).
- [ ] `blocking_issues` is empty; review any `DEGRADED` dependency even
      though it does not block readiness.

## 5. Test Execution

- [ ] Full suite passes: `pytest tests` — zero failures, zero
      unaccounted-for regressions against the last known-good count.
- [ ] `tests/operations/test_alembic_environment.py` passes (exercises a
      real `alembic upgrade`/`downgrade` cycle).
- [ ] `tests/stress/` passes (large-batch CRUD, concurrent reads,
      deterministic ordering).
- [ ] `tests/lifecycle/` passes (full bootstrap/shutdown sequence against
      a real `FastAPI` app instance).
- [ ] Throwaway virtual environment and `__pycache__`/`.pytest_cache`
      cleaned up after the run (no test artifacts committed).

## 6. Documentation Verification

- [ ] `docs/architecture/BACKEND_ARCHITECTURE.md` reflects the actual
      deployed component set (service catalog, repository catalog) —
      regenerate the table if a new domain package has been added since
      Sprint 54.
- [ ] `docs/database/MIGRATIONS.md` reflects the current migration chain
      (baseline plus any revisions added since).
- [ ] Every domain engine's own module docstring (the authoritative
      design record for that engine's formulas/rules) is current — this
      checklist does not duplicate that detail and should not be trusted
      as a substitute for it.

## 7. Clean Environment Verification

- [ ] Deployment target has no leftover throwaway virtualenvs, `.env`
      files with development defaults, or stale `alembic_version` rows
      from a different schema lineage.
- [ ] `ENVIRONMENT` is set correctly for the target
      (`development`/`staging`/`production`) — checked by
      `ConfigurationValidationService`'s `supported_value:environment`
      check (advisory `WARNING`, not blocking, if unrecognized).
- [ ] No development-only defaults remain (`change-me` secrets,
      `localhost` hosts) unless this genuinely is a local/dev deployment.
- [ ] Logs are structured and reaching wherever this deployment expects
      them (`app.state.structured_logger` — `StdlibStructuredLogger`
      wraps the standard `logging` module; confirm the deployment's log
      aggregation actually captures stdout/stderr or whatever handler is
      configured).

## Sign-off

Record who ran this checklist, against which environment, and the date,
before promoting a build to production.

| Item | Status | Notes |
|---|---|---|
| Migrations applied | | |
| Configuration validated | | |
| Dependencies validated | | |
| Bootstrap validated | | |
| Tests executed | | |
| Documentation verified | | |
| Clean environment verified | | |
