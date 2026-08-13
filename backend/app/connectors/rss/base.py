"""Abstract contract for pure, read-only data connectors.

A connector's only responsibility is fetching raw data from a single
external source and returning it unmodified. Connectors never normalize,
deduplicate, store, or interpret what they fetch — those concerns belong to
agents and services built on top of a connector.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

__all__ = ["BaseConnector"]


class BaseConnector(ABC):
    """Abstract base class every data connector must implement.

    A connector is not an agent: it has no lifecycle hooks, no memory
    access, and no schema-based input/output contract. It is a minimal,
    single-purpose I/O boundary around one external source.
    """

    @abstractmethod
    def fetch(self) -> Any:
        """Fetch and return raw data from the configured source, unmodified."""
        raise NotImplementedError
