"""Future Nightshift/Engine interfaces. Never substitute synthetic AI success."""

from dataclasses import dataclass
from typing import Protocol

from app.integrations.zetaris import IntegrationNotConfigured


@dataclass(frozen=True)
class Completion:
    text: str
    model_id: str
    receipt_id: str


class InferenceProvider(Protocol):
    def complete(self, *, prompt: str, model_id: str) -> Completion:
        ...


@dataclass(frozen=True)
class MeterlessStatus:
    status: str = "not_configured"
    nightshift: str = "not_configured"
    engine: str = "not_configured"
    reason: str = "Nightshift inference and a real Meterless Engine remain to be implemented."


class MeterlessClient:
    def status(self) -> MeterlessStatus:
        return MeterlessStatus()

    def complete(self, *, prompt: str, model_id: str) -> Completion:
        raise IntegrationNotConfigured(self.status().reason)
