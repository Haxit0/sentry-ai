"""Planner agent: turns an incident into structured investigation tasks.

The model proposes tasks over the allowlisted tools. A coverage policy then adds any tool a
sound investigation cannot skip, and recalled H-MEM memories add verification tasks. Every
step records its origin, so the trace shows what the model planned and what policy added.
"""

from typing import Any

from app.agents.llm import RecordingModel, as_text, compact
from app.agents.schemas import PlanStep, RecalledMemory
from app.agents.tools import TOOL_DESCRIPTIONS

REQUIRED_TOOLS = ("get_supplier", "get_inventory", "get_orders", "run_disruption_simulation", "get_recovery_options")
MAX_MODEL_TASKS = 8

SYSTEM = (
    "You are the Planner agent of Sentry AI, a supply-chain disruption investigator. "
    "Break the incident into investigation tasks. Each task asks one question and names exactly one tool "
    "from the list. Do not answer the questions and do not invent data. "
    'Reply with JSON only: {"tasks": [{"question": "...", "tool": "<tool name>"}]}'
)


def plan(model: RecordingModel, incident: str, memories: list[RecalledMemory]) -> tuple[list[PlanStep], list[str]]:
    """Return plan steps and notes about anything the planner output lacked."""
    tools = "\n".join(f"- {name}: {text}" for name, text in TOOL_DESCRIPTIONS.items())
    memory_note = ""
    if memories:
        memory_note = (
            "\nPrior investigation memory (context only: it may be stale, never reuse its figures):\n"
            + "\n".join(f"- [{m.memory_id}] {m.content}" for m in memories)
        )
    user = f"Incident: {incident}\nTools:\n{tools}{memory_note}\nReturn 4 to 7 tasks."
    payload, _ = model.ask_json(SYSTEM, user, max_tokens=500)
    steps, notes = _model_steps(payload)

    planned_tools = {step.tool for step in steps}
    for tool in REQUIRED_TOOLS:
        if tool not in planned_tools:
            steps.append(PlanStep(task_id="", question=f"Coverage: {TOOL_DESCRIPTIONS[tool]}", tool=tool, origin="coverage_policy"))
            notes.append(f"planner omitted required tool {tool}; added by coverage policy")
    for memory in memories:
        for tag in memory.tags:
            if tag.startswith("strategy:"):
                steps.append(PlanStep(
                    task_id="", tool="get_recovery_options", origin="memory",
                    question=f"Memory {memory.memory_id} chose {tag.split(':', 1)[1]} before; re-check it against current costs",
                ))
    return [step.model_copy(update={"task_id": f"T{index}"}) for index, step in enumerate(steps, 1)], notes


def _model_steps(payload: dict[str, Any] | None) -> tuple[list[PlanStep], list[str]]:
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list):
        return [], ["planner output was not a JSON task list; plan built by coverage policy"]
    steps: list[PlanStep] = []
    rejected: list[str] = []
    for task in tasks[:MAX_MODEL_TASKS]:
        tool = task.get("tool") if isinstance(task, dict) else None
        question = as_text(task.get("question"), 200) if isinstance(task, dict) else ""
        if tool not in TOOL_DESCRIPTIONS or not question:
            rejected.append(compact(task)[:80])
            continue
        steps.append(PlanStep(task_id="", question=question, tool=tool, origin="planner"))
    notes = [f"rejected planner task (unknown tool or empty question): {item}" for item in rejected]
    return steps, notes
