"""Private helper shared by `ConfigurationValidationService` and
`StartupValidationService` for building a `ValidationReport` from a list
of `ValidationCheck`s — not part of this package's public API."""

from __future__ import annotations

from datetime import datetime

from app.operations.validation.models import ValidationCheck, ValidationReport, ValidationSeverity

__all__ = ["build_report"]


def build_report(checks: list[ValidationCheck], generated_at: datetime) -> ValidationReport:
    failed = [check for check in checks if not check.passed]
    blocking = [check for check in failed if check.severity == ValidationSeverity.ERROR]
    total = len(checks)
    summary = f"{total - len(failed)}/{total} check(s) passed" if total else "no checks performed"
    if failed:
        summary += f"; {len(failed)} failed ({len(blocking)} blocking)"
    return ValidationReport(checks=tuple(checks), passed=not blocking, generated_at=generated_at, summary=summary)
