"""Unit tests for the BaseConnector abstract contract."""

from __future__ import annotations

import pytest

from app.connectors.rss.base import BaseConnector
from app.connectors.rss.rss_connector import RSSConnector


def test_base_connector_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        BaseConnector()  # type: ignore[abstract]


def test_rss_connector_is_a_base_connector() -> None:
    connector = RSSConnector(feed_url="https://example.com/feed.xml")
    assert isinstance(connector, BaseConnector)
