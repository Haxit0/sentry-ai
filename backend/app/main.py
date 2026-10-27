"""Run with: uvicorn app.main:app --host 127.0.0.1 --port 8000."""

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agents.router import router as investigations_router
from app.data.repository import FixtureRepository
from app.schemas import HealthResponse, Order, SimulationRequest, SimulationResponse, Supplier
from app.services.simulation import UnknownSupplierError, simulate


app = FastAPI(title="Sentry AI", version="0.1.0", description="Deterministic synthetic supply-chain What-If simulator.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)
app.include_router(investigations_router)


def get_repository() -> FixtureRepository:
    return FixtureRepository()


@app.get("/api/health", response_model=HealthResponse)
def health(repository: FixtureRepository = Depends(get_repository)) -> HealthResponse:
    return HealthResponse(as_of_date=repository.snapshot().as_of_date)


@app.get("/api/suppliers", response_model=list[Supplier])
def suppliers(repository: FixtureRepository = Depends(get_repository)) -> list[Supplier]:
    return repository.snapshot().suppliers


@app.get("/api/orders", response_model=list[Order])
def orders(repository: FixtureRepository = Depends(get_repository)) -> list[Order]:
    return repository.snapshot().orders


@app.post("/api/simulations", response_model=SimulationResponse)
def simulations(request: SimulationRequest, repository: FixtureRepository = Depends(get_repository)) -> SimulationResponse:
    try:
        return simulate(request, repository)
    except UnknownSupplierError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
