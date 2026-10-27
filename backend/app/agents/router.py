"""Additive `POST /api/investigations`; the frozen v1 endpoints are untouched.

Configuration comes from the environment, or from METERLESS_*/SENTRY_* keys in the repository-root
`.env` without overriding real environment variables. Missing configuration or any Nightshift or
H-MEM failure is a 503 with the reason; there is no fallback answer.
"""

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.agents.schemas import InvestigationRequest, InvestigationResponse
from app.data.repository import DataRepository, FixtureRepository
from app.integrations.hmem import HMemEngine, default_state_dir
from app.integrations.meterless import InferenceProvider, MeterlessConfig, MeterlessError, NightshiftClient
from app.integrations.zetaris import IntegrationNotConfigured
from app.services.agent_investigation import investigate
from app.services.simulation import UnknownSupplierError

REPO_ENV = Path(__file__).resolve().parents[3] / ".env"
router = APIRouter()
# One investigation at a time: the persistent H-MEM store is a single JSON state file.
_memory_lock = threading.Lock()


def load_env(path: Path | None = None) -> None:
    path = path or REPO_ENV
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip().startswith(("METERLESS_", "SENTRY_")):
            os.environ.setdefault(key.strip(), value.strip())


@dataclass
class AgentRuntime:
    provider: InferenceProvider
    requested_model: str
    memory: HMemEngine | None


@contextmanager
def live_runtime() -> Iterator[AgentRuntime]:
    load_env()
    config = MeterlessConfig.from_env()
    with NightshiftClient(config) as client, _memory_lock, HMemEngine(default_state_dir()) as memory:
        yield AgentRuntime(client, config.model, memory)


def get_agent_runtime() -> Iterator[AgentRuntime]:
    try:
        with live_runtime() as runtime:
            yield runtime
    except IntegrationNotConfigured as exc:
        raise HTTPException(status_code=503, detail=f"Agent runtime not configured: {exc}") from exc
    except MeterlessError as exc:
        raise HTTPException(status_code=503, detail=f"{type(exc).__name__}: {exc}") from exc


def get_investigation_repository() -> DataRepository:
    return FixtureRepository()


@router.post("/api/investigations", response_model=InvestigationResponse)
def investigations(
    request: InvestigationRequest,
    runtime: AgentRuntime = Depends(get_agent_runtime),
    repository: DataRepository = Depends(get_investigation_repository),
) -> InvestigationResponse:
    try:
        return investigate(request, repository, runtime.provider, requested_model=runtime.requested_model, memory=runtime.memory)
    except UnknownSupplierError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MeterlessError as exc:
        raise HTTPException(status_code=503, detail=f"{type(exc).__name__}: {exc}") from exc
