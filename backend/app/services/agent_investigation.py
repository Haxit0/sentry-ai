"""Planner -> Investigator -> Evaluator investigation with H-MEM memory and bounded retries.

1. Recall related prior investigations from the Meterless H-MEM engine (planning context only).
2. Planner (Nightshift model) writes structured tasks; policy fills required coverage.
3. Investigator runs the tools, then the model drafts a claim citing evidence.
4. Evaluator checks the claim against tool outputs and exact Decimal results; a failure becomes
   explicit feedback and a re-investigation, at most `max_attempts` drafts.
5. Only a validated claim becomes a recommendation, is stored in H-MEM, and scores recalled memories.
Model or engine failures raise; nothing here falls back to canned text.
"""

import uuid

from app.agents import investigator, planner
from app.agents.evaluator import evaluate, parse_money
from app.agents.llm import RecordingModel
from app.agents.schemas import (
    Attempt, Claim, Incident, InvestigationRequest, InvestigationResponse, MemoryConflict, MemoryUsage,
    RecalledMemory, Validation,
)
from app.agents.tools import InvestigationTools
from app.data.repository import DataRepository, FixtureRepository
from app.integrations.hmem import UPSTREAM_COMMIT, HMemEngine
from app.integrations.meterless import InferenceProvider
from app.services.simulation import UnknownSupplierError

MAX_ATTEMPTS = 3
RECALL_THRESHOLD = 0.45  # H-MEM final-score cut: same-supplier history scores ~0.55, other suppliers ~0.39
DISCLAIMER = (
    "Agent investigation over {source} data. Inference runs through Meterless Nightshift; investigation memory "
    "uses the Meterless H-MEM engine. Every financial figure comes from the deterministic simulator; the model "
    "plans, explains and cites, and is checked before any recommendation. Recommendations only: no purchases, "
    "shipments or customer orders are changed."
)


def memory_key(supplier_id: str, name: str, sku: str, delay_days: int) -> str:
    return f"Supplier disruption {supplier_id} {name} {sku} delayed {delay_days} days"


def investigate(
    request: InvestigationRequest, repository: DataRepository, provider: InferenceProvider, *,
    requested_model: str, memory: HMemEngine | None = None, max_attempts: int = MAX_ATTEMPTS,
) -> InvestigationResponse:
    tools = InvestigationTools(repository, request.supplier_id, request.delay_days)
    supplier = tools.supplier
    if supplier is None:
        raise UnknownSupplierError(f"Unknown supplier: {request.supplier_id}")
    investigation_id = f"inv-{uuid.uuid4().hex[:12]}"
    model = RecordingModel(provider, requested_model)
    incident = (f"Supplier {supplier.supplier_id} ({supplier.name}, SKU {supplier.sku}) reports its scheduled restock "
                f"on {supplier.restock_date} will arrive {request.delay_days} days late. Evaluation date {tools.data.as_of_date}.")
    key = memory_key(supplier.supplier_id, supplier.name, supplier.sku, request.delay_days)

    recalled: list[RecalledMemory] = []
    if memory is not None:
        hits = memory.query(key, top_n=3, threshold=RECALL_THRESHOLD)
        recalled = [RecalledMemory(
            memory_id=hit["memory"]["id"], relevance=round(hit["relevance"], 4), content=hit["memory"]["content"],
            tags=hit["memory"]["tags"], use="planning context only; every figure re-verified against current tools",
        ) for hit in hits["memories"]]

    steps, plan_notes = planner.plan(model, incident, recalled)
    investigator.execute(tools, steps)

    attempts: list[Attempt] = []
    feedback: list[str] = []
    claim: Claim | None = None
    evaluation = None
    for number in range(1, max_attempts + 1):
        claim = investigator.draft(model, tools, incident, feedback)
        if claim is None:
            feedback = ["the reply was not a JSON object; reply with the JSON object only"]
            attempts.append(Attempt(attempt=number, outcome="unparseable", failed_checks=["claim_parsed"],
                                    retry_reason=feedback[0] if number < max_attempts else None, claim=None))
            continue
        # Re-investigation: fetch anything still missing and resolve every cited evidence id via the tool.
        investigator.reinvestigate(tools, [t for t in planner.REQUIRED_TOOLS if not tools.called(t)], claim.evidence_ids)
        evaluation = evaluate(claim, tools)
        if evaluation.passed:
            attempts.append(Attempt(attempt=number, outcome="validated", failed_checks=[], retry_reason=None, claim=claim))
            break
        feedback = evaluation.feedback
        attempts.append(Attempt(attempt=number, outcome="rejected", failed_checks=evaluation.failed,
                                retry_reason="; ".join(evaluation.feedback) if number < max_attempts else None, claim=claim))

    validated = evaluation is not None and evaluation.passed and attempts[-1].outcome == "validated"
    result = tools.simulation
    unresolved = [] if validated else (
        [f"{check.check}: {check.detail}" for check in evaluation.checks if not check.passed] if evaluation and attempts[-1].outcome == "rejected"
        else ["no parseable claim from the investigator model"]
    )
    memory_usage = None
    if memory is not None:
        memory_usage = _remember(memory, investigation_id, key, recalled, claim if validated else None, tools)

    return InvestigationResponse(
        investigation_id=investigation_id,
        status="validated" if validated else "unresolved",
        incident=Incident(supplier_id=supplier.supplier_id, supplier_name=supplier.name, sku=supplier.sku,
                          delay_days=request.delay_days, summary=incident),
        as_of_date=result.as_of_date,
        disrupted_restock_date=result.disrupted_restock_date,
        plan=steps,
        plan_notes=plan_notes,
        tool_calls=tools.calls,
        affected_orders=result.affected_orders,
        estimated_penalty_exposure_gbp=result.estimated_penalty_exposure_gbp,
        recovery_options=result.recovery_options,
        calculated_recommendation=result.recommended_strategy,
        recommended_strategy=claim.recommended_strategy if validated else None,
        recommended_total_cost_gbp=parse_money(claim.recommended_total_cost_gbp) if validated else None,
        explanation=claim.explanation if validated else None,
        supporting_evidence_ids=claim.evidence_ids if validated else [],
        hypotheses=claim.assumptions if claim else [],
        claim=claim,
        validation=Validation(
            passed=validated, attempts_used=len(attempts), max_attempts=max_attempts,
            checks=evaluation.checks if evaluation else [], attempts=attempts, unresolved=unresolved,
        ),
        model=model.usage(),
        memory=memory_usage,
        data_source=_source_name(repository),
        disclaimer=DISCLAIMER.format(source=_source_name(repository)),
    )


def _remember(
    memory: HMemEngine, investigation_id: str, key: str, recalled: list[RecalledMemory],
    claim: Claim | None, tools: InvestigationTools, *, provenance_refs: tuple[str, ...] = (),
) -> MemoryUsage:
    stored_id = None
    feedback: list[dict[str, str]] = []
    conflicts: list[MemoryConflict] = []
    if claim is not None:
        result = tools.simulation
        affected = [o.order_id for o in result.affected_orders]
        stored = memory.add(
            f"{key}. Validated recommendation {claim.recommended_strategy}. Affected orders {', '.join(affected) or 'none'}. "
            f"Exposure GBP {result.estimated_penalty_exposure_gbp:.2f}; {claim.recommended_strategy} total GBP "
            f"{claim.recommended_total_cost_gbp} as of {result.as_of_date} (re-verify: figures go stale). "
            f"Evidence {', '.join(claim.evidence_ids)}.",
            source=f"sentry-ai://investigations/{investigation_id}",
            tags=[f"supplier:{result.supplier_id}", f"sku:{tools.supplier.sku}", f"strategy:{claim.recommended_strategy}",
                  f"delay:{result.delay_days}"],
            confidence=0.9, layer="long_term", memory_type="factual", refs=[*claim.evidence_ids, *provenance_refs],
            label=f"validated investigation {investigation_id}",
        )
        stored_id = stored["id"]
        # Score recalled memories: did the prior decision hold under current data?
        for item in recalled:
            prior = next((t.split(":", 1)[1] for t in item.tags if t.startswith("strategy:")), None)
            kind = "helpful" if prior == claim.recommended_strategy else "not_helpful"
            memory.feedback(item.memory_id, kind)
            feedback.append({"memory_id": item.memory_id, "kind": kind,
                             "reason": f"prior {prior}; current validated {claim.recommended_strategy}"})
        conflicts = [
            MemoryConflict(memory_a=c["memoryA"], memory_b=c["memoryB"], reason=c["reason"], confidence=round(c["confidence"], 3))
            for c in memory.scan_conflicts() if stored_id in (c["memoryA"], c["memoryB"])
        ]
    info = memory.version_info
    return MemoryUsage(
        implementation=f"{info['package']} {info['version']} (Meterless/Meterless@{UPSTREAM_COMMIT[:7]})",
        persistent=memory.persistent, query=key, recalled=recalled, stored_memory_id=stored_id,
        feedback=feedback, conflicts=conflicts, ledger=memory.stats()["ledger"],
    )


def _source_name(repository: DataRepository) -> str:
    if isinstance(repository, FixtureRepository):
        return "fixture"
    name = type(repository).__name__
    return "zetaris" if name.startswith("Zetaris") else name
