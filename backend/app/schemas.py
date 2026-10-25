"""Version-one shared API contract. Coordinate changes with all three owners."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, StrictInt


Money = Annotated[
    Decimal,
    Field(max_digits=14, decimal_places=2),
    PlainSerializer(lambda value: format(value, ".2f"), return_type=str, when_used="json"),
]
Cost = Annotated[Money, Field(ge=0)]
Strategy = Literal["accept_delay", "expedite_shipping", "alternative_supplier"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExpediteOption(ContractModel):
    days_saved: int = Field(ge=0)
    capacity_units: int = Field(ge=0)
    fixed_fee_gbp: Cost
    per_unit_fee_gbp: Cost


class AlternativeSupplier(ContractModel):
    supplier_name: str
    lead_time_days: int = Field(ge=0)
    capacity_units: int = Field(ge=0)
    fixed_fee_gbp: Cost
    unit_premium_gbp: Cost


class Supplier(ContractModel):
    supplier_id: str
    name: str
    sku: str
    restock_date: date
    replenishment_quantity: int = Field(gt=0)
    expedite: ExpediteOption
    alternative: AlternativeSupplier


class Order(ContractModel):
    order_id: str
    customer_name: str
    supplier_id: str
    sku: str
    quantity: int = Field(gt=0)
    promised_date: date
    penalty_per_day_gbp: Cost


class Inventory(ContractModel):
    sku: str
    on_hand_units: int = Field(ge=0)


class DemoData(ContractModel):
    as_of_date: date
    suppliers: list[Supplier]
    orders: list[Order]
    inventory: list[Inventory]


class SimulationRequest(ContractModel):
    supplier_id: str = Field(min_length=1, max_length=80)
    delay_days: StrictInt = Field(ge=0, le=30)


class AffectedOrder(Order):
    inventory_allocated: int = Field(ge=0)
    shortfall_units: int = Field(ge=0)
    expected_delivery_date: date
    delay_days: int = Field(ge=0)
    estimated_penalty_gbp: Cost


class RecoveryOption(ContractModel):
    strategy: Strategy
    residual_penalty_gbp: Cost
    action_cost_gbp: Cost
    total_estimated_cost_gbp: Cost
    saving_vs_no_action_gbp: Money
    details: str


class Evidence(ContractModel):
    evidence_id: str
    source: str
    description: str


class SimulationResponse(ContractModel):
    supplier_id: str
    delay_days: int
    as_of_date: date
    disrupted_restock_date: date
    affected_orders: list[AffectedOrder]
    estimated_penalty_exposure_gbp: Cost
    recovery_options: list[RecoveryOption]
    recommended_strategy: Strategy
    evidence: list[Evidence]
    execution_mode: Literal["fixture"] = "fixture"
    agent_status: Literal["not_configured"] = "not_configured"
    disclaimer: str


class IntegrationStatuses(ContractModel):
    zetaris: Literal["not_configured"] = "not_configured"
    meterless: Literal["not_configured"] = "not_configured"


class HealthResponse(ContractModel):
    status: Literal["ok"] = "ok"
    execution_mode: Literal["fixture"] = "fixture"
    as_of_date: date
    agent_status: Literal["not_configured"] = "not_configured"
    integrations: IntegrationStatuses = Field(default_factory=IntegrationStatuses)
