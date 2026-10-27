"""Investigation report models for the additive `POST /api/investigations` endpoint.

Kept apart from the frozen v1 `app/schemas.py`; reuses its money encoding and record types.
"""

from datetime import date
from typing import Any, Literal

from pydantic import Field

from app.schemas import AffectedOrder, ContractModel, Cost, Money, RecoveryOption, SimulationRequest, Strategy


class InvestigationRequest(SimulationRequest):
    """Same validation as a simulation: supplier 1–80 chars, strict integer delay 0–30."""


class PlanStep(ContractModel):
    task_id: str
    question: str
    tool: str
    origin: Literal["planner", "coverage_policy", "memory"]


class ToolCall(ContractModel):
    call_id: str
    task_id: str
    tool: str
    arguments: dict[str, str | int]
    status: Literal["ok", "not_found", "error"]
    summary: str
    evidence_ids: list[str]
    result: Any


class Check(ContractModel):
    check: str
    passed: bool
    detail: str


class Claim(ContractModel):
    """What the investigator model asserted, kept verbatim for audit beside the checks."""
    recommended_strategy: str | None
    affected_order_ids: list[str]
    penalty_exposure_gbp: str | None
    recommended_total_cost_gbp: str | None
    evidence_ids: list[str]
    explanation: str
    assumptions: list[str]


class Attempt(ContractModel):
    attempt: int
    outcome: Literal["validated", "rejected", "unparseable"]
    failed_checks: list[str]
    retry_reason: str | None
    claim: Claim | None


class Validation(ContractModel):
    passed: bool
    attempts_used: int
    max_attempts: int
    checks: list[Check]
    attempts: list[Attempt]
    unresolved: list[str]


class ModelUsage(ContractModel):
    runtime: Literal["meterless-nightshift"] = "meterless-nightshift"
    requested_model: str
    models_used: list[str]
    providers: list[str]
    receipt_ids: list[str]
    signed_receipts: int
    calls: int
    prompt_tokens: int
    completion_tokens: int


class RecalledMemory(ContractModel):
    memory_id: str
    relevance: float
    content: str
    tags: list[str]
    use: str


class MemoryConflict(ContractModel):
    memory_a: str
    memory_b: str
    reason: str
    confidence: float


class MemoryUsage(ContractModel):
    engine: Literal["H-MEM"] = "H-MEM"
    implementation: str
    persistent: bool
    query: str
    recalled: list[RecalledMemory]
    stored_memory_id: str | None
    feedback: list[dict[str, str]]
    conflicts: list[MemoryConflict]
    ledger: dict[str, int]


class Incident(ContractModel):
    supplier_id: str
    supplier_name: str
    sku: str
    delay_days: int
    summary: str


class InvestigationResponse(ContractModel):
    investigation_id: str
    status: Literal["validated", "unresolved"]
    incident: Incident
    as_of_date: date
    disrupted_restock_date: date
    plan: list[PlanStep]
    plan_notes: list[str]
    tool_calls: list[ToolCall]
    affected_orders: list[AffectedOrder]
    estimated_penalty_exposure_gbp: Cost
    recovery_options: list[RecoveryOption]
    calculated_recommendation: Strategy = Field(description="Deterministic simulator ranking; a calculated fact")
    recommended_strategy: Strategy | None = Field(description="Agent recommendation; null unless validation passed")
    recommended_total_cost_gbp: Money | None
    explanation: str | None
    supporting_evidence_ids: list[str]
    hypotheses: list[str]
    claim: Claim | None
    validation: Validation
    model: ModelUsage
    memory: MemoryUsage | None
    data_source: str
    disclaimer: str
