"""Explicit investigation tools over the repository boundary and the deterministic simulator.

Every tool reads one pinned snapshot, so all calls in an investigation see the same records,
whether the repository is the fixture or Zetaris. Arguments come from the validated incident,
never from model text. Each call is recorded with its output for the evidence trace.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.agents.schemas import ToolCall
from app.data.repository import DataRepository
from app.schemas import DemoData, SimulationRequest, SimulationResponse
from app.services.simulation import simulate


class PinnedRepository:
    """Takes one snapshot and serves it for the rest of the investigation."""

    def __init__(self, repository: DataRepository) -> None:
        self.source = repository
        self._data: DemoData | None = None

    def snapshot(self) -> DemoData:
        if self._data is None:
            self._data = self.source.snapshot()
        return self._data.model_copy(deep=True)

    def __getattr__(self, name: str) -> Any:
        # Pass provenance helpers such as Developer 1's `evidence_source` through to the real repository.
        return getattr(self.source, name)


@dataclass(frozen=True)
class ToolOutcome:
    status: str
    summary: str
    evidence_ids: list[str]
    result: Any


TOOL_DESCRIPTIONS = {
    "get_supplier": "Supplier record: SKU, scheduled restock, expedite and alternative offers.",
    "get_inventory": "On-hand units for the supplier's SKU.",
    "get_orders": "Customer orders that depend on this supplier.",
    "run_disruption_simulation": "Deterministic FIFO simulation: affected orders and penalty exposure.",
    "get_recovery_options": "Deterministic cost of accept_delay, expedite_shipping, alternative_supplier.",
    "get_evidence": "Look up one evidence record by evidence_id.",
}


@dataclass
class InvestigationTools:
    repository: DataRepository
    supplier_id: str
    delay_days: int
    calls: list[ToolCall] = field(default_factory=list)
    _simulation: SimulationResponse | None = None

    def __post_init__(self) -> None:
        self.repository = PinnedRepository(self.repository)
        self.data = self.repository.snapshot()
        self.supplier = next((s for s in self.data.suppliers if s.supplier_id == self.supplier_id), None)
        self._handlers: dict[str, Callable[..., ToolOutcome]] = {
            "get_supplier": self._get_supplier, "get_inventory": self._get_inventory, "get_orders": self._get_orders,
            "run_disruption_simulation": self._run_simulation, "get_recovery_options": self._get_recovery_options,
            "get_evidence": self._get_evidence,
        }

    @property
    def names(self) -> list[str]:
        return list(self._handlers)

    @property
    def simulation(self) -> SimulationResponse:
        if self._simulation is None:
            self._simulation = simulate(SimulationRequest(supplier_id=self.supplier_id, delay_days=self.delay_days), self.repository)
        return self._simulation

    def evidence_index(self) -> dict[str, Any]:
        return {item.evidence_id: item for item in self.simulation.evidence}

    def called(self, tool: str) -> bool:
        return any(call.tool == tool and call.status == "ok" for call in self.calls)

    def call(self, task_id: str, tool: str, **arguments: str | int) -> ToolCall:
        handler = self._handlers.get(tool)
        if handler is None:
            raise ValueError(f"Unknown tool: {tool}")
        try:
            outcome = handler(**arguments)
        except Exception as exc:  # recorded, never hidden; the evaluator sees the failed call
            outcome = ToolOutcome("error", f"{type(exc).__name__}: {exc}", [], None)
        record = ToolCall(
            call_id=f"call-{len(self.calls) + 1}", task_id=task_id, tool=tool, arguments=dict(arguments),
            status=outcome.status, summary=outcome.summary, evidence_ids=outcome.evidence_ids, result=outcome.result,
        )
        self.calls.append(record)
        return record

    def call_default(self, task_id: str, tool: str) -> ToolCall:
        """Bind a tool's arguments from the incident, never from model output."""
        if tool == "get_inventory":
            return self.call(task_id, tool, sku=self.supplier.sku)
        if tool in ("run_disruption_simulation", "get_recovery_options"):
            return self.call(task_id, tool, supplier_id=self.supplier_id, delay_days=self.delay_days)
        if tool == "get_evidence":
            return self.call(task_id, tool, evidence_id=f"supplier:{self.supplier_id}")
        return self.call(task_id, tool, supplier_id=self.supplier_id)

    def _get_supplier(self, supplier_id: str) -> ToolOutcome:
        supplier = next((s for s in self.data.suppliers if s.supplier_id == supplier_id), None)
        if supplier is None:
            return ToolOutcome("not_found", f"No supplier {supplier_id}", [], None)
        return ToolOutcome(
            "ok", f"{supplier.name} supplies {supplier.sku}; {supplier.replenishment_quantity} units due {supplier.restock_date}",
            [f"supplier:{supplier.supplier_id}"], supplier.model_dump(mode="json"),
        )

    def _get_inventory(self, sku: str) -> ToolOutcome:
        item = next((i for i in self.data.inventory if i.sku == sku), None)
        if item is None:
            return ToolOutcome("not_found", f"No inventory record for {sku}", [], None)
        return ToolOutcome("ok", f"{item.on_hand_units} on-hand units of {sku} as of {self.data.as_of_date}",
                           [f"inventory:{sku}"], item.model_dump(mode="json"))

    def _get_orders(self, supplier_id: str) -> ToolOutcome:
        orders = sorted((o for o in self.data.orders if o.supplier_id == supplier_id), key=lambda o: (o.promised_date, o.order_id))
        return ToolOutcome(
            "ok" if orders else "not_found", f"{len(orders)} orders depend on {supplier_id}: {', '.join(o.order_id for o in orders)}",
            [f"order:{o.order_id}" for o in orders], [o.model_dump(mode="json") for o in orders],
        )

    def _run_simulation(self, supplier_id: str, delay_days: int) -> ToolOutcome:
        result = self.simulation
        affected = [o.order_id for o in result.affected_orders]
        return ToolOutcome(
            "ok",
            f"Restock moves to {result.disrupted_restock_date}; {len(affected)} late orders "
            f"({', '.join(affected) or 'none'}); exposure GBP {result.estimated_penalty_exposure_gbp:.2f}",
            [f"order:{order_id}" for order_id in affected],
            {
                "disrupted_restock_date": result.disrupted_restock_date.isoformat(),
                "affected_orders": [o.model_dump(mode="json") for o in result.affected_orders],
                "estimated_penalty_exposure_gbp": f"{result.estimated_penalty_exposure_gbp:.2f}",
            },
        )

    def _get_recovery_options(self, supplier_id: str, delay_days: int) -> ToolOutcome:
        result = self.simulation
        ranked = ", ".join(f"{o.strategy} GBP {o.total_estimated_cost_gbp:.2f}" for o in result.recovery_options)
        return ToolOutcome(
            "ok", f"Ranked cheapest first: {ranked}", [f"recovery:{supplier_id}"],
            [o.model_dump(mode="json") for o in result.recovery_options],
        )

    def _get_evidence(self, evidence_id: str) -> ToolOutcome:
        item = self.evidence_index().get(evidence_id)
        if item is None:
            return ToolOutcome("not_found", f"No evidence record {evidence_id}", [], None)
        return ToolOutcome("ok", item.description, [evidence_id], item.model_dump(mode="json"))
