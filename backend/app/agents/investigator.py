"""Investigator agent: executes planned tool calls, then drafts an evidence-cited claim.

Tools run with arguments bound from the incident. The model sees only recorded tool outputs
and writes a structured claim; it never computes money itself and is told to copy figures.
"""

from typing import Any

from app.agents.llm import RecordingModel, as_str_list, as_text, compact, first
from app.agents.schemas import Claim, PlanStep
from app.agents.tools import InvestigationTools

SYSTEM = (
    "You are the Investigator agent of Sentry AI. You receive tool outputs from a supply-chain investigation. "
    "Use ONLY these outputs. Copy money figures exactly as written; never calculate or estimate new numbers, "
    "and never use percentages (quote saving_gbp instead). "
    "Cite evidence_ids that appear in the outputs. Separate facts from assumptions. "
    "Reply with JSON only: "
    '{"recommended_strategy": "<accept_delay|expedite_shipping|alternative_supplier>", '
    '"affected_order_ids": ["..."], "penalty_exposure_gbp": "0.00", "recommended_total_cost_gbp": "0.00", '
    '"evidence_ids": ["..."], "explanation": "2-4 sentences on why", "assumptions": ["..."]}'
)


def execute(tools: InvestigationTools, steps: list[PlanStep]) -> None:
    for step in steps:
        tools.call_default(step.task_id, step.tool)


def reinvestigate(tools: InvestigationTools, missing_tools: list[str], evidence_ids: list[str]) -> None:
    """Re-run what the evaluator found missing and look up every cited evidence id."""
    for tool in missing_tools:
        tools.call_default("RETRY", tool)
    for evidence_id in evidence_ids:
        if not any(c.tool == "get_evidence" and c.arguments.get("evidence_id") == evidence_id for c in tools.calls):
            tools.call("RETRY", "get_evidence", evidence_id=evidence_id)


def tool_digest(tools: InvestigationTools) -> str:
    lines = []
    for call in tools.calls:
        if call.status != "ok" or call.tool == "get_evidence":
            continue
        lines.append(f"[{call.call_id}] {call.tool}: {call.summary} (evidence_ids: {', '.join(call.evidence_ids) or 'none'})")
    simulation = tools.simulation
    lines.append("Deterministic results (authoritative):")
    lines.append(compact({
        "affected_orders": [
            {"order_id": o.order_id, "late_days": o.delay_days, "penalty_gbp": f"{o.estimated_penalty_gbp:.2f}"}
            for o in simulation.affected_orders
        ],
        "penalty_exposure_gbp": f"{simulation.estimated_penalty_exposure_gbp:.2f}",
        "recovery_options_cheapest_first": [
            {"strategy": o.strategy, "total_gbp": f"{o.total_estimated_cost_gbp:.2f}", "action_cost_gbp": f"{o.action_cost_gbp:.2f}",
             "residual_penalty_gbp": f"{o.residual_penalty_gbp:.2f}", "saving_gbp": f"{o.saving_vs_no_action_gbp:.2f}"}
            for o in simulation.recovery_options
        ],
        "evidence_ids": [item.evidence_id for item in simulation.evidence],
    }))
    return "\n".join(lines)


def draft(model: RecordingModel, tools: InvestigationTools, incident: str, feedback: list[str]) -> Claim | None:
    user = f"Incident: {incident}\nTool outputs:\n{tool_digest(tools)}"
    if feedback:
        user += "\nYour previous answer failed validation. Fix exactly these problems:\n" + "\n".join(f"- {item}" for item in feedback)
    payload, _ = model.ask_json(SYSTEM, user, max_tokens=600)
    return to_claim(payload)


def to_claim(payload: dict[str, Any] | None) -> Claim | None:
    if not isinstance(payload, dict):
        return None
    money = lambda value: None if value is None else str(value)[:40]  # noqa: E731
    strategy = first(payload, "recommended_strategy", "strategy")
    return Claim(
        recommended_strategy=str(strategy)[:60] if strategy is not None else None,
        affected_order_ids=as_str_list(first(payload, "affected_order_ids", "affected_orders")),
        penalty_exposure_gbp=money(first(payload, "penalty_exposure_gbp", "estimated_penalty_exposure_gbp")),
        recommended_total_cost_gbp=money(first(payload, "recommended_total_cost_gbp", "total_cost_gbp")),
        evidence_ids=as_str_list(first(payload, "evidence_ids", "evidence")),
        explanation=as_text(payload.get("explanation")),
        assumptions=as_str_list(payload.get("assumptions"), limit=8),
    )
