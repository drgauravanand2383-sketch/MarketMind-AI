"""StartupValidationService: validates that application bootstrap wired
every required component correctly.

Composes `ConfigurationValidationService` (injected, not re-implemented —
"Reuse existing services") for the settings-level checks, and adds three
checks specific to the DI/bootstrap graph itself: every required
component was registered (non-`None`) and none twice, no two different
names alias the same constructed instance, and every repository
package's model metadata is discoverable with no table-name collisions
(reusing `app.operations.migrations.discovery`, the same collection point
`alembic/env.py` uses — never a second, divergent list).

Never constructs or reconstructs any component itself — every check is a
pure function of whatever `(name, instance)` pairs and settings objects
the caller (`app.bootstrap.bootstrap_application_state`) passes in.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Callable

from app.config.models import AnthropicSettings, APISettings, LLMSettings, LoggingSettings, PostgreSQLSettings, RSSSettings
from app.operations.migrations.discovery import collect_table_names, duplicate_table_names
from app.operations.validation._report import build_report
from app.operations.validation.configuration import ConfigurationValidationService
from app.operations.validation.models import ValidationCheck, ValidationReport, ValidationSeverity

__all__ = ["StartupValidationService", "DEFAULT_REQUIRED_COMPONENTS"]

DEFAULT_REQUIRED_COMPONENTS: frozenset[str] = frozenset(
    {
        "watchlist_repository",
        "watchlist_service",
        "screening_repository",
        "screening_engine",
        "market_data_provider",
        "normalization_service",
        "signal_repository",
        "signal_detection_service",
        "alert_rule_repository",
        "alert_repository",
        "alert_service",
        "recommendation_repository",
        "recommendation_service",
        "strategy_repository",
        "strategy_service",
        "risk_repository",
        "risk_service",
        "backtesting_repository",
        "backtesting_service",
        "explainability_repository",
        "explainability_service",
    }
)


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class StartupValidationService:
    def __init__(
        self,
        configuration_service: ConfigurationValidationService,
        *,
        now_fn: Callable[[], datetime] = _default_now,
    ) -> None:
        self._configuration_service = configuration_service
        self._now_fn = now_fn

    def validate_components(
        self,
        components: tuple[tuple[str, object | None], ...],
        *,
        required: frozenset[str] = DEFAULT_REQUIRED_COMPONENTS,
    ) -> ValidationReport:
        """Validate dependency injection wiring and repository
        registration: every `required` name is present and non-`None`,
        no name is registered more than once, and no two different names
        alias the exact same instance (a copy-paste wiring bug class)."""
        checks: list[ValidationCheck] = []

        name_counts = Counter(name for name, _ in components)
        for name, count in sorted(name_counts.items()):
            if count > 1:
                checks.append(
                    ValidationCheck(
                        name=f"duplicate_registration:{name}",
                        passed=False,
                        severity=ValidationSeverity.ERROR,
                        message=f"{name!r} was registered {count} times",
                    )
                )

        instances_by_id: dict[int, list[str]] = defaultdict(list)
        for name, instance in components:
            if instance is not None:
                instances_by_id[id(instance)].append(name)
        for names in instances_by_id.values():
            if len(names) > 1:
                checks.append(
                    ValidationCheck(
                        name=f"aliased_instance:{'+'.join(sorted(names))}",
                        passed=False,
                        severity=ValidationSeverity.WARNING,
                        message=f"the same instance is registered under multiple names: {sorted(names)}",
                    )
                )

        registered = dict(components)
        for name in sorted(required):
            present = registered.get(name) is not None
            checks.append(
                ValidationCheck(
                    name=f"registered:{name}",
                    passed=present,
                    severity=ValidationSeverity.ERROR,
                    message="registered" if present else "MISSING - not registered or failed to construct",
                )
            )

        return build_report(checks, self._now_fn())

    def validate_metadata_discovery(self) -> ValidationReport:
        """Validate that every repository package's `Base.metadata` is
        discoverable and that no two packages claim the same table name."""
        table_names = collect_table_names()
        duplicates = duplicate_table_names()
        checks = [
            ValidationCheck(
                name="model_metadata_discovery",
                passed=len(table_names) > 0,
                severity=ValidationSeverity.ERROR,
                message=f"discovered {len(table_names)} table(s)",
            ),
            ValidationCheck(
                name="model_metadata_uniqueness",
                passed=not duplicates,
                severity=ValidationSeverity.ERROR,
                message="no duplicate table names" if not duplicates else f"duplicate table names: {list(duplicates)}",
            ),
        ]
        return build_report(checks, self._now_fn())

    def validate_configuration(
        self,
        *,
        environment: str,
        postgres: PostgreSQLSettings,
        anthropic: AnthropicSettings | None,
        logging_settings: LoggingSettings,
        llm: LLMSettings,
        api: APISettings,
        rss: RSSSettings,
    ) -> ValidationReport:
        return self._configuration_service.validate(
            environment=environment,
            postgres=postgres,
            anthropic=anthropic,
            logging_settings=logging_settings,
            llm=llm,
            api=api,
            rss=rss,
        )

    def validate_full(
        self,
        components: tuple[tuple[str, object | None], ...],
        *,
        required: frozenset[str] = DEFAULT_REQUIRED_COMPONENTS,
        environment: str,
        postgres: PostgreSQLSettings,
        anthropic: AnthropicSettings | None,
        logging_settings: LoggingSettings,
        llm: LLMSettings,
        api: APISettings,
        rss: RSSSettings,
    ) -> ValidationReport:
        """Run every startup check and return one combined report."""
        component_report = self.validate_components(components, required=required)
        metadata_report = self.validate_metadata_discovery()
        configuration_report = self.validate_configuration(
            environment=environment,
            postgres=postgres,
            anthropic=anthropic,
            logging_settings=logging_settings,
            llm=llm,
            api=api,
            rss=rss,
        )
        all_checks = list(component_report.checks) + list(metadata_report.checks) + list(configuration_report.checks)
        return build_report(all_checks, self._now_fn())
