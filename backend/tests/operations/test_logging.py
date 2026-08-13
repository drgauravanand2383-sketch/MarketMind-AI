"""Tests for the structured logging abstraction."""

from __future__ import annotations

import logging

from app.operations.logging.logger import InMemoryStructuredLogger, StdlibStructuredLogger
from app.operations.logging.models import LogCategory, LogLevel


def test_in_memory_logger_captures_every_emitted_record() -> None:
    logger = InMemoryStructuredLogger()

    logger.info(LogCategory.STARTUP, "bootstrap_started")
    logger.error(LogCategory.REPOSITORY, "connection_failed", host="db")

    assert len(logger.records) == 2
    assert logger.records[0].category == LogCategory.STARTUP
    assert logger.records[0].level == LogLevel.INFO
    assert logger.records[1].level == LogLevel.ERROR
    assert logger.records[1].context == {"host": "db"}


def test_in_memory_logger_records_for_filters_by_category() -> None:
    logger = InMemoryStructuredLogger()
    logger.info(LogCategory.STARTUP, "a")
    logger.info(LogCategory.SERVICE, "b")
    logger.warning(LogCategory.STARTUP, "c")

    startup_records = logger.records_for(LogCategory.STARTUP)

    assert len(startup_records) == 2
    assert {record.event for record in startup_records} == {"a", "c"}


def test_every_convenience_method_uses_the_matching_level() -> None:
    logger = InMemoryStructuredLogger()
    logger.debug(LogCategory.APPLICATION, "d")
    logger.info(LogCategory.APPLICATION, "i")
    logger.warning(LogCategory.APPLICATION, "w")
    logger.error(LogCategory.APPLICATION, "e")
    logger.critical(LogCategory.APPLICATION, "c")

    levels = [record.level for record in logger.records]

    assert levels == [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]


def test_records_have_a_timestamp() -> None:
    logger = InMemoryStructuredLogger()
    logger.info(LogCategory.VALIDATION, "checked")

    assert logger.records[0].timestamp is not None


def test_stdlib_logger_output_is_valid_structured_json(caplog) -> None:  # type: ignore[no-untyped-def]
    import json

    stdlib_logger = logging.getLogger("test.structured_logger.json")
    structured = StdlibStructuredLogger(stdlib_logger)

    with caplog.at_level(logging.INFO, logger="test.structured_logger.json"):
        structured.info(LogCategory.SERVICE, "service_called", service="risk")

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload["event"] == "service_called"
    assert payload["category"] == "SERVICE"
    assert payload["context"] == {"service": "risk"}
