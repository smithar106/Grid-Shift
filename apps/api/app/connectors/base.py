"""Connector contracts.

Every external data source must expose the same normalized interface, so the ingestion
service and the optimizer never learn where a number came from. Adding a source means
implementing ``fetch`` and returning observations that already satisfy the shared
contracts — nothing downstream changes.

A connector must **never** substitute synthetic values when its upstream fails. Silent
substitution would make a fabricated number indistinguishable from a real one, which
breaks the project's central guarantee that every result is traceable to its input data.
Failure is always an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.schemas.enums import DataSource, DataStatus
from app.schemas.observations import Observation

__all__ = ["Connector", "ConnectorError", "ConnectorResult", "UpstreamUnavailable"]


class ConnectorError(RuntimeError):
    """Base class for connector failures."""


class UpstreamUnavailable(ConnectorError):
    """The upstream service could not be reached, or answered with an error.

    Raised instead of returning partial or fabricated data.
    """


@dataclass(frozen=True, slots=True)
class ConnectorResult:
    """Normalized output of any connector."""

    source: DataSource
    data_status: DataStatus
    retrieved_at: datetime
    location_id: str
    observations: tuple[Observation, ...]
    from_cache: bool = False

    @property
    def metrics(self) -> tuple[str, ...]:
        return tuple(sorted({observation.metric.value for observation in self.observations}))


@runtime_checkable
class Connector(Protocol):
    """A source of normalized observations."""

    source: DataSource

    async def fetch(self, *, location_id: str, **kwargs: object) -> ConnectorResult:
        """Retrieve and normalize observations.

        Raises:
            UpstreamUnavailable: if the source cannot be read.
        """
        ...
