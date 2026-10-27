"""Planner -> Investigator -> Evaluator workflow with scripted model replies (no network).

These prove control flow, validation and retries. They are NOT evidence that a real model
works; see scripts/agent_smoke.py and tests/test_agent_live.py for real Nightshift runs.
"""

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.agents import router as agent_router
from app.agents.llm import extract_json
from app.agents.schemas import InvestigationRequest
from app.agents.tools import InvestigationTools
from app.data.repository import FixtureRepository
from app.integrations.meterless import Completion, MeterlessUnavailable
from app.main import app
from app.schemas import DemoData, SimulationRequest
from app.services.agent_investigation import investigate
from app.services.simulation import UnknownSupplierError, simulate
from test_meterless import CLOCK, needs_node

PLAN = json.dumps({"tasks": [
    {"question": "Which customer orders depend on Alpha?", "tool": "get_orders"},
    {"question": "How much stock is on hand?", "tool": "get_inventory"},
    {"question": "Which orders become late and what is the exposure?", "tool": "run_disruption_simulation"},
    {"question": "What do the recovery options cost?", "tool": "get_recovery_options"},
]})


def claim(**overrides) -> str:
    body = {
        "recommended_strategy": "expedite_shipping", "affected_order_ids": ["ORD-1002"],
        "penalty_exposure_gbp": "500.00", "recommended_total_cost_gbp": "160.00",
        "evidence_ids": ["order:ORD-1002", "recovery:SUP-ALPHA", "supplier:SUP-ALPHA"],
        "explanation": "ORD-1002 completes 5 days late, exposing GBP 500.00 in penalties. Expediting costs GBP 160.00 "
                       "and removes the penalty, saving GBP 340.00 against accepting the delay.",
        "assumptions": ["Calendar days; transit excluded"],
    }
    body.update(overrides)
    return "```json\n" + json.dumps(body) + "\n```"


class ScriptedModel:
    """Stands in for NightshiftClient.chat: returns queued replies and records every prompt."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def chat(self, messages: Sequence[Mapping[str, str]], *, max_tokens: int = 512, temperature: float = 0.0) -> Completion:
        self.prompts.append(messages[-1]["content"])
        if not self.replies:
            raise AssertionError("model called more times than scripted")
        return Completion(text=self.replies.pop(0), model_id="mock/model", receipt_id=f"rcpt-{len(self.prompts)}",
                          requested_model="meterless/local", provider="mock", prompt_tokens=10, completion_tokens=5)


def run(model: ScriptedModel, supplier_id: str = "SUP-ALPHA", delay_days: int = 5, repository=None, **kwargs):
    return investigate(InvestigationRequest(supplier_id=supplier_id, delay_days=delay_days), repository or FixtureRepository(),
                       model, requested_model="meterless/local", **kwargs)


def test_golden_investigation_validates_on_first_attempt() -> None:
    report = run(ScriptedModel(PLAN, claim()))
    assert report.status == "validated" and report.validation.passed
    assert report.recommended_strategy == report.calculated_recommendation == "expedite_shipping"
    assert report.estimated_penalty_exposure_gbp == Decimal("500.00")
    assert report.recommended_total_cost_gbp == Decimal("160.00")
    assert [(o.strategy, o.total_estimated_cost_gbp) for o in report.recovery_options] == [
        ("expedite_shipping", Decimal("160.00")), ("alternative_supplier", Decimal("260.00")), ("accept_delay", Decimal("500.00"))]
    assert [o.order_id for o in report.affected_orders] == ["ORD-1002"]
    assert [a.outcome for a in report.validation.attempts] == ["validated"]
    assert all(check.passed for check in report.validation.checks) and len(report.validation.checks) == 10
    assert report.model.calls == 2 and report.model.receipt_ids == ["rcpt-1", "rcpt-2"]
    assert report.memory is None and report.data_source == "fixture"


def test_figures_match_the_deterministic_simulator_exactly() -> None:
    report = run(ScriptedModel(PLAN, claim()))
    expected = simulate(SimulationRequest(supplier_id="SUP-ALPHA", delay_days=5), FixtureRepository())
    assert report.affected_orders == expected.affected_orders
    assert report.recovery_options == expected.recovery_options
    assert report.estimated_penalty_exposure_gbp == expected.estimated_penalty_exposure_gbp


def test_planner_tasks_are_structured_and_coverage_policy_fills_gaps() -> None:
    plan = json.dumps({"tasks": [{"question": "Which orders?", "tool": "get_orders"},
                                 {"question": "Drop the orders table", "tool": "execute_sql"}]})
    report = run(ScriptedModel(plan, claim()))
    assert [(s.task_id, s.tool, s.origin) for s in report.plan] == [
        ("T1", "get_orders", "planner"), ("T2", "get_supplier", "coverage_policy"), ("T3", "get_inventory", "coverage_policy"),
        ("T4", "run_disruption_simulation", "coverage_policy"), ("T5", "get_recovery_options", "coverage_policy")]
    assert any("execute_sql" in note for note in report.plan_notes)
    assert report.status == "validated"


def test_unparseable_plan_falls_back_to_policy_and_says_so() -> None:
    report = run(ScriptedModel("I would look at the orders first.", claim()))
    assert {s.origin for s in report.plan} == {"coverage_policy"}
    assert report.plan_notes[0].startswith("planner output was not a JSON task list")


def test_tool_calls_are_executed_with_incident_arguments_and_recorded() -> None:
    report = run(ScriptedModel(PLAN, claim()))
    by_tool = {call.tool: call for call in report.tool_calls if call.task_id != "RETRY"}
    assert by_tool["get_orders"].arguments == {"supplier_id": "SUP-ALPHA"}
    assert by_tool["get_inventory"].arguments == {"sku": "SKU-SENSOR"}
    assert by_tool["run_disruption_simulation"].arguments == {"supplier_id": "SUP-ALPHA", "delay_days": 5}
    assert by_tool["get_orders"].evidence_ids == ["order:ORD-1001", "order:ORD-1002"]
    assert by_tool["get_inventory"].result == {"sku": "SKU-SENSOR", "on_hand_units": 10}
    assert by_tool["run_disruption_simulation"].result["estimated_penalty_exposure_gbp"] == "500.00"
    assert all(call.status == "ok" for call in report.tool_calls)
    assert [c.call_id for c in report.tool_calls] == [f"call-{i}" for i in range(1, len(report.tool_calls) + 1)]


def test_every_cited_evidence_id_is_resolved_through_get_evidence() -> None:
    report = run(ScriptedModel(PLAN, claim()))
    lookups = {c.arguments["evidence_id"]: c for c in report.tool_calls if c.tool == "get_evidence"}
    assert set(report.supporting_evidence_ids) <= set(lookups)
    assert lookups["order:ORD-1002"].result["source"] == "backend/app/data/demo_data.json#orders/ORD-1002"
    simulation_ids = {e.evidence_id for e in simulate(SimulationRequest(supplier_id="SUP-ALPHA", delay_days=5), FixtureRepository()).evidence}
    assert set(report.supporting_evidence_ids) <= simulation_ids


@pytest.mark.parametrize(("overrides", "failed"), [
    ({"penalty_exposure_gbp": "450.00"}, ["exposure_matches"]),
    ({"recommended_total_cost_gbp": "£150"}, ["cost_matches"]),
    ({"recommended_strategy": "alternative_supplier", "recommended_total_cost_gbp": "260.00"}, ["strategy_matches_calculation"]),
    ({"recommended_strategy": "buy_the_supplier"}, ["strategy_exists", "strategy_matches_calculation", "cost_matches"]),
    ({"affected_order_ids": ["ORD-1002", "ORD-9999"]}, ["order_ids_valid", "affected_orders_match"]),
    ({"affected_order_ids": ["ORD-1001", "ORD-1002"]}, ["affected_orders_match"]),
    ({"evidence_ids": ["order:ORD-1002", "recovery:SUP-ALPHA", "contract:ACME-7"]}, ["evidence_exists"]),
    ({"explanation": "Expedite costs GBP 160.00 and saves GBP 999.00."}, ["explanation_grounded"]),
    ({"explanation": "Expedite costs GBP 160.00, a 68% saving."}, ["explanation_grounded"]),
    ({"explanation": "ORD-4242 is late; expedite costs GBP 160.00."}, ["explanation_grounded"]),
    ({"explanation": "Two orders are impacted (ORD-1001, ORD-1002). Expedite costs GBP 160.00."}, ["explanation_grounded"]),
    ({"explanation": ""}, ["explanation_grounded"]),
])
def test_incorrect_or_conflicting_claims_are_flagged_then_corrected(overrides: dict, failed: list[str]) -> None:
    model = ScriptedModel(PLAN, claim(**overrides), claim())
    report = run(model)
    first = report.validation.attempts[0]
    assert first.outcome == "rejected" and first.failed_checks == failed
    assert first.claim is not None and first.retry_reason
    assert report.status == "validated" and report.validation.attempts_used == 2
    assert "failed validation" in model.prompts[-1]  # the retry carries the evaluator's reasons


def test_missing_supporting_evidence_triggers_reinvestigation_feedback() -> None:
    model = ScriptedModel(PLAN, claim(evidence_ids=["supplier:SUP-ALPHA"]), claim())
    report = run(model)
    assert report.validation.attempts[0].failed_checks == ["evidence_supports_recommendation"]
    assert "order:ORD-1002" in model.prompts[-1] and "recovery:SUP-ALPHA" in model.prompts[-1]
    assert report.status == "validated"


def test_unparseable_claim_is_retried_with_explicit_reason() -> None:
    model = ScriptedModel(PLAN, "Expedite is best, trust me.", claim())
    report = run(model)
    assert [a.outcome for a in report.validation.attempts] == ["unparseable", "validated"]
    assert report.validation.attempts[0].failed_checks == ["claim_parsed"]


def test_retries_are_bounded_and_exhaustion_fails_safely() -> None:
    model = ScriptedModel(PLAN, *[claim(penalty_exposure_gbp="450.00")] * 3)
    report = run(model, max_attempts=3)
    assert report.status == "unresolved" and not report.validation.passed
    assert [a.outcome for a in report.validation.attempts] == ["rejected"] * 3
    assert report.validation.attempts[-1].retry_reason is None
    assert report.recommended_strategy is None and report.explanation is None and report.recommended_total_cost_gbp is None
    assert report.supporting_evidence_ids == []
    assert any(item.startswith("exposure_matches") for item in report.validation.unresolved)
    assert report.calculated_recommendation == "expedite_shipping"  # calculated facts are still reported as facts
    assert model.replies == [] and report.model.calls == 4


def test_zero_delay_investigation_recommends_accepting() -> None:
    reply = claim(recommended_strategy="accept_delay", affected_order_ids=[], penalty_exposure_gbp="0.00",
                  recommended_total_cost_gbp="0.00", evidence_ids=["recovery:SUP-ALPHA"],
                  explanation="No order becomes late, so accepting the delay costs GBP 0.00.")
    report = run(ScriptedModel(PLAN, reply), delay_days=0)
    assert report.status == "validated" and report.recommended_strategy == "accept_delay"
    assert report.affected_orders == []


def test_unknown_supplier_is_rejected_before_any_model_call() -> None:
    model = ScriptedModel()
    with pytest.raises(UnknownSupplierError):
        run(model, supplier_id="SUP-UNKNOWN")
    assert model.prompts == []


def test_runtime_failure_propagates_instead_of_inventing_a_report() -> None:
    class Down:
        def chat(self, *args, **kwargs):
            raise MeterlessUnavailable("Nightshift unreachable")

    with pytest.raises(MeterlessUnavailable):
        run(Down())


def test_extract_json_tolerates_fences_chatter_and_braces_in_strings() -> None:
    assert extract_json('Sure!\n```json\n{"a": "x } y", "b": {"c": 1}}\n```') == {"a": "x } y", "b": {"c": 1}}
    assert extract_json('{"a": "quote \\" } inside"}') == {"a": 'quote " } inside'}
    assert extract_json("no json here") is None and extract_json("[1, 2]") is None


class RelabelledRepository:
    """A non-fixture repository with its own provenance, as Zetaris provides."""

    def snapshot(self) -> DemoData:
        return FixtureRepository().snapshot()

    def evidence_source(self, collection: str, record_id: str) -> str:
        return f"other://{collection}/{record_id}"


def test_agent_is_repository_agnostic() -> None:
    report = run(ScriptedModel(PLAN, claim()), repository=RelabelledRepository())
    assert report.status == "validated" and report.data_source == "RelabelledRepository"


def test_investigation_over_zetaris_repository_rows() -> None:
    pytest.importorskip("app.data.zetaris_repository", reason="needs Developer 1's Zetaris repository (PR #5)")
    fake = pytest.importorskip("test_zetaris").FakeZetaris()
    report = run(ScriptedModel(PLAN, claim()), repository=fake.repository())
    assert report.status == "validated" and report.data_source == "zetaris"
    assert report.estimated_penalty_exposure_gbp == Decimal("500.00")
    assert any(call.result and str(call.result.get("source", "")).startswith("zetaris://")
               for call in report.tool_calls if call.tool == "get_evidence")


def test_tools_pin_one_snapshot_per_investigation() -> None:
    class Counting(FixtureRepository):
        calls = 0

        def snapshot(self) -> DemoData:
            Counting.calls += 1
            return super().snapshot()

    tools = InvestigationTools(Counting(), "SUP-ALPHA", 5)
    for tool in ("get_supplier", "get_orders", "run_disruption_simulation", "get_recovery_options"):
        tools.call_default("T", tool)
    assert Counting.calls == 1


# --- Meterless H-MEM engine in the workflow (real engine, scripted model) ---

@needs_node
def test_memory_from_a_prior_investigation_is_recalled_and_shapes_the_plan(tmp_path) -> None:
    from app.integrations.hmem import HMemEngine

    with HMemEngine(tmp_path, clock_ms=CLOCK) as memory:
        first = run(ScriptedModel(PLAN, claim()), memory=memory)
        assert first.memory.recalled == [] and first.memory.stored_memory_id == "mem-1"
        assert not any(step.origin == "memory" for step in first.plan)

        reply = claim(penalty_exposure_gbp="600.00", recommended_total_cost_gbp="260.00",
                      explanation="ORD-1002 completes 6 days late, exposing GBP 600.00. Expediting costs GBP 260.00.")
        model = ScriptedModel(PLAN, reply)
        second = run(model, delay_days=6, memory=memory)

    assert [m.memory_id for m in second.memory.recalled] == ["mem-1"]
    assert "[mem-1]" in model.prompts[0]                                     # the planner saw the memory
    memory_steps = [step for step in second.plan if step.origin == "memory"]
    assert len(memory_steps) == 1 and "expedite_shipping" in memory_steps[0].question
    assert second.memory.feedback == [{"memory_id": "mem-1", "kind": "helpful",
                                       "reason": "prior expedite_shipping; current validated expedite_shipping"}]
    assert second.memory.stored_memory_id == "mem-2"
    assert [(c.memory_a, c.memory_b) for c in second.memory.conflicts] == [("mem-1", "mem-2")]
    assert second.memory.ledger == {"create": 2, "read": 1, "feedback": 1, "conflict_detected": 1}


@needs_node
def test_stale_memory_figures_cannot_override_current_data(tmp_path) -> None:
    from app.integrations.hmem import HMemEngine

    with HMemEngine(tmp_path, clock_ms=CLOCK) as memory:
        run(ScriptedModel(PLAN, claim()), memory=memory)                    # remembers GBP 500 / 160 at +5 days
        stale = claim(explanation="As last time, exposure is GBP 500.00 and expediting costs GBP 160.00.")
        report = run(ScriptedModel(PLAN, stale, stale, stale), delay_days=6, memory=memory)

    assert report.memory.recalled[0].memory_id == "mem-1"
    assert report.status == "unresolved"
    assert set(report.validation.attempts[0].failed_checks) == {"exposure_matches", "cost_matches", "explanation_grounded"}
    assert report.memory.stored_memory_id is None                            # unvalidated results are never remembered
    assert report.estimated_penalty_exposure_gbp == Decimal("600.00")


@needs_node
def test_memory_whose_strategy_no_longer_holds_is_marked_not_helpful(tmp_path) -> None:
    from app.integrations.hmem import HMemEngine

    with HMemEngine(tmp_path, clock_ms=CLOCK) as memory:
        run(ScriptedModel(PLAN, claim()), memory=memory)
        long_delay = claim(recommended_strategy="alternative_supplier", penalty_exposure_gbp="3000.00",
                           recommended_total_cost_gbp="260.00",
                           explanation="ORD-1002 would be 30 days late (GBP 3000.00). The alternative supplier costs GBP 260.00.")
        report = run(ScriptedModel(PLAN, long_delay), delay_days=30, memory=memory)

    assert report.status == "validated" and report.recommended_strategy == "alternative_supplier"
    assert report.memory.feedback[0]["memory_id"] == "mem-1" and report.memory.feedback[0]["kind"] == "not_helpful"


# --- HTTP endpoint ---

client = TestClient(app)


@pytest.fixture
def scripted_runtime():
    def install(*replies: str):
        runtime = agent_router.AgentRuntime(ScriptedModel(*replies), "meterless/local", None)
        app.dependency_overrides[agent_router.get_agent_runtime] = lambda: runtime
        return runtime
    yield install
    app.dependency_overrides.clear()


def test_investigation_endpoint_returns_evidence_backed_report(scripted_runtime) -> None:
    scripted_runtime(PLAN, claim())
    response = client.post("/api/investigations", json={"supplier_id": "SUP-ALPHA", "delay_days": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "validated" and body["recommended_strategy"] == "expedite_shipping"
    assert body["estimated_penalty_exposure_gbp"] == "500.00" and body["recommended_total_cost_gbp"] == "160.00"
    assert body["recovery_options"][0]["total_estimated_cost_gbp"] == "160.00"
    assert body["validation"]["passed"] is True and body["tool_calls"][0]["call_id"] == "call-1"


def test_investigation_endpoint_unknown_supplier_is_404(scripted_runtime) -> None:
    scripted_runtime()
    response = client.post("/api/investigations", json={"supplier_id": "SUP-UNKNOWN", "delay_days": 5})
    assert response.status_code == 404 and response.json() == {"detail": "Unknown supplier: SUP-UNKNOWN"}


@pytest.mark.parametrize("payload", [{"supplier_id": "SUP-ALPHA", "delay_days": "5"}, {"supplier_id": "SUP-ALPHA", "delay_days": 31},
                                     {"supplier_id": "", "delay_days": 5}, {"supplier_id": "SUP-ALPHA", "delay_days": 5, "x": 1}])
def test_investigation_endpoint_validates_requests(scripted_runtime, payload: dict) -> None:
    scripted_runtime()
    assert client.post("/api/investigations", json=payload).status_code == 422


def test_investigation_endpoint_without_configuration_is_503(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    for key in ("METERLESS_BASE_URL", "METERLESS_API_TOKEN", "METERLESS_TOKEN_FILE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(agent_router, "REPO_ENV", tmp_path / "absent.env")
    response = client.post("/api/investigations", json={"supplier_id": "SUP-ALPHA", "delay_days": 5})
    assert response.status_code == 503 and "not configured" in response.json()["detail"]


def test_runtime_outage_mid_investigation_is_503(scripted_runtime) -> None:
    class Down:
        def chat(self, *args, **kwargs):
            raise MeterlessUnavailable("Nightshift unreachable at http://127.0.0.1:18088/v1")

    app.dependency_overrides[agent_router.get_agent_runtime] = lambda: agent_router.AgentRuntime(Down(), "meterless/local", None)
    response = client.post("/api/investigations", json={"supplier_id": "SUP-ALPHA", "delay_days": 5})
    assert response.status_code == 503 and response.json()["detail"].startswith("MeterlessUnavailable")


def test_existing_simulation_endpoint_is_unchanged() -> None:
    response = client.post("/api/simulations", json={"supplier_id": "SUP-ALPHA", "delay_days": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["estimated_penalty_exposure_gbp"] == "500.00" and body["recommended_strategy"] == "expedite_shipping"
    assert body["execution_mode"] == "fixture" and body["agent_status"] == "not_configured"
