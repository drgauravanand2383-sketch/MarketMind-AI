"""Operational infrastructure: migrations, logging, metrics, profiling,
health, and validation. No investment/business logic lives here — every
module in this package supports production readiness (Sprint 54) for the
business logic that lives in the domain packages (`app.screening`,
`app.recommendations`, `app.risk`, etc.)."""
