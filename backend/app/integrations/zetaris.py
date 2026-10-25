"""Future authenticated, read-only Zetaris adapter. No network calls in fixture mode."""

from dataclasses import dataclass

from app.schemas import DemoData


class IntegrationNotConfigured(RuntimeError):
    """Raised rather than inventing successful integration output."""


@dataclass(frozen=True)
class IntegrationStatus:
    status: str = "not_configured"
    reason: str = "Zetaris integration is not implemented in this starter."


class ZetarisRepository:
    """Implement DataRepository.snapshot with bounded queries, auth and provenance."""

    def status(self) -> IntegrationStatus:
        return IntegrationStatus()

    def snapshot(self) -> DemoData:
        raise IntegrationNotConfigured(self.status().reason)
