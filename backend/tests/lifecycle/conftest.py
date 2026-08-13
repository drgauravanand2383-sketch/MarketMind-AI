"""Test-only isolation for the lifecycle tests.

`app.bootstrap.configure_logging` calls `logging.basicConfig(force=True)`
— correct, intended behavior for a real process that configures logging
exactly once at startup, but this test module is the only place in the
whole suite that calls `bootstrap_application_state()` (and therefore
`configure_logging`) repeatedly within a single pytest process. Left
unchecked, each call wipes out every handler already attached to the root
logger — including pytest's own `caplog` handler — corrupting logging
assertions in unrelated test modules that happen to run afterward in the
same session. Save and restore the root logger's handlers/level around
each test in this module only; no production code is touched.
"""

from __future__ import annotations

import logging

import pytest


@pytest.fixture(autouse=True)
def _restore_root_logging_state():
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    try:
        yield
    finally:
        root.handlers = original_handlers
        root.setLevel(original_level)
