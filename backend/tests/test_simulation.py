"""Known-answer API, inventory, recovery, and disclosure checks."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.data.repository import FixtureRepository
from app.integrations.meterless import MeterlessClient
from app.integrations.zetaris import IntegrationNotConfigured, ZetarisRepository
from app.main import app
from app.schemas import DemoData, SimulationRequest, SimulationResponse
from app.services.simulation import simulate


client = TestClient(app)


class StaticRepository:
    def __init__(self, data: DemoData) -> None:
        self.data = data

    def snapshot(self) -> DemoData:
        return self.data.model_copy(deep=True)


def request(supplier_id: str = "SUP-ALPHA", delay_days: int = 5) -> dict:
    response = client.post("/api/simulations", json={"supplier_id": supplier_id, "delay_days": delay_days})
    assert response.status_code == 200
    return response.json()


def test_health_is_healthy_and_discloses_fixture_mode() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok", "execution_mode": "fixture", "as_of_date": "2026-10-25",
        "agent_status": "not_configured",
        "integrations": {"zetaris": "not_configured", "meterless": "not_configured"},
    }


def test_supplier_and_order_listing() -> None:
    suppliers = client.get("/api/suppliers")
    orders = client.get("/api/orders")
    assert suppliers.status_code == orders.status_code == 200
    assert [item["supplier_id"] for item in suppliers.json()] == ["SUP-ALPHA", "SUP-BETA", "SUP-GAMMA"]
    assert len(orders.json()) == 6
    assert len({item["sku"] for item in orders.json()}) == 3
    assert suppliers.json()[0]["expedite"]["fixed_fee_gbp"] == "100.00"


def test_five_day_alpha_golden_fixture() -> None:
    golden = json.loads((Path(__file__).parent / "fixtures" / "alpha_five_day.json").read_text())
    response = client.post("/api/simulations", json=golden["request"])
    assert response.status_code == 200
    result = response.json()
    for field in ("as_of_date", "disrupted_restock_date", "estimated_penalty_exposure_gbp", "recommended_strategy"):
        assert result[field] == golden[field]
    assert [item["order_id"] for item in result["affected_orders"]] == golden["affected_order_ids"]
    assert [item["strategy"] for item in result["recovery_options"]] == golden["ranked_strategies"]
    assert [item["total_estimated_cost_gbp"] for item in result["recovery_options"]] == golden["ranked_total_costs_gbp"]
    affected = result["affected_orders"][0]
    assert affected["inventory_allocated"] == 0
    assert affected["shortfall_units"] == 20
    assert affected["delay_days"] == 5
    assert affected["estimated_penalty_gbp"] == "500.00"
    cheapest = result["recovery_options"][0]
    assert cheapest["residual_penalty_gbp"] == "0.00"
    assert cheapest["action_cost_gbp"] == "160.00"
    assert cheapest["saving_vs_no_action_gbp"] == "340.00"
    assert "ORD-1001" not in golden["affected_order_ids"]


@pytest.mark.parametrize("supplier_id", ["SUP-ALPHA", "SUP-BETA", "SUP-GAMMA"])
def test_no_delay_is_zero_exposure_and_stable_accept_delay_tie(supplier_id: str) -> None:
    result = request(supplier_id, 0)
    assert result["affected_orders"] == []
    assert result["estimated_penalty_exposure_gbp"] == "0.00"
    assert result["recommended_strategy"] == "accept_delay"
    assert [item["strategy"] for item in result["recovery_options"]] == ["accept_delay", "expedite_shipping", "alternative_supplier"]
    assert all(item["total_estimated_cost_gbp"] == "0.00" for item in result["recovery_options"])


def test_partial_inventory_allocates_to_earliest_promised_orders() -> None:
    result = request("SUP-BETA", 5)
    first, second = result["affected_orders"]
    assert (first["order_id"], first["inventory_allocated"], first["shortfall_units"]) == ("ORD-1003", 5, 7)
    assert (second["order_id"], second["inventory_allocated"], second["shortfall_units"]) == ("ORD-1004", 0, 8)
    assert (first["delay_days"], second["delay_days"]) == (4, 2)
    assert result["estimated_penalty_exposure_gbp"] == "250.00"
    assert result["recommended_strategy"] == "expedite_shipping"
    assert result["recovery_options"][0]["total_estimated_cost_gbp"] == "145.00"


def test_limited_alternative_capacity_cannot_complete_a_partial_order() -> None:
    result = request("SUP-GAMMA", 5)
    alternative = next(item for item in result["recovery_options"] if item["strategy"] == "alternative_supplier")
    assert alternative["action_cost_gbp"] == "136.00"  # 80 fixed + 8 × 7 premium
    assert alternative["residual_penalty_gbp"] == "220.00"  # 8/10 units cannot complete order
    assert alternative["total_estimated_cost_gbp"] == "356.00"
    assert alternative["saving_vs_no_action_gbp"] == "-136.00"
    assert "8/10" in alternative["details"]


def test_expensive_actions_are_not_recommended_for_small_disruptions() -> None:
    result = request("SUP-ALPHA", 1)
    assert result["estimated_penalty_exposure_gbp"] == "100.00"
    assert result["recommended_strategy"] == "accept_delay"


def test_long_disruption_changes_recommendation_to_alternative() -> None:
    result = request("SUP-ALPHA", 30)
    assert result["recommended_strategy"] == "alternative_supplier"
    assert result["recovery_options"][0]["total_estimated_cost_gbp"] == "260.00"


@pytest.mark.parametrize("supplier_id", ["SUP-ALPHA", "SUP-BETA", "SUP-GAMMA"])
@pytest.mark.parametrize("delay_days", [0, 1, 5, 30])
def test_cost_identities_and_non_worsening_penalties(supplier_id: str, delay_days: int) -> None:
    result = request(supplier_id, delay_days)
    exposure = Decimal(result["estimated_penalty_exposure_gbp"])
    assert exposure == sum((Decimal(item["estimated_penalty_gbp"]) for item in result["affected_orders"]), Decimal("0.00"))
    totals = []
    for option in result["recovery_options"]:
        residual = Decimal(option["residual_penalty_gbp"])
        total = Decimal(option["total_estimated_cost_gbp"])
        assert total == residual + Decimal(option["action_cost_gbp"])
        assert Decimal(option["saving_vs_no_action_gbp"]) == exposure-total
        assert residual <= exposure
        totals.append(total)
    assert totals == sorted(totals)
    assert result["recommended_strategy"] == result["recovery_options"][0]["strategy"]
    SimulationResponse.model_validate(result)


@pytest.mark.parametrize("payload", [
    {"supplier_id": "SUP-ALPHA", "delay_days": -1},
    {"supplier_id": "SUP-ALPHA", "delay_days": 31},
    {"supplier_id": "SUP-ALPHA", "delay_days": 5.5},
    {"supplier_id": "SUP-ALPHA", "delay_days": "5"},
    {"supplier_id": "SUP-ALPHA", "delay_days": True},
    {"supplier_id": "SUP-ALPHA", "delay_days": None},
    {"supplier_id": "", "delay_days": 5},
    {"supplier_id": "SUP-ALPHA"},
    {"delay_days": 5},
    {"supplier_id": "SUP-ALPHA", "delay_days": 5, "secret": "unexpected"},
])
def test_invalid_inputs_return_422(payload: dict) -> None:
    response = client.post("/api/simulations", json=payload)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_unknown_supplier_returns_404() -> None:
    response = client.post("/api/simulations", json={"supplier_id": "UNKNOWN", "delay_days": 5})
    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown supplier: UNKNOWN"}


def test_response_discloses_fixture_and_no_agents_with_traceable_evidence() -> None:
    result = request()
    assert result["execution_mode"] == "fixture"
    assert result["agent_status"] == "not_configured"
    assert "Synthetic" in result["disclaimer"]
    assert "No purchases" in result["disclaimer"]
    assert {item["evidence_id"] for item in result["evidence"]} >= {
        "supplier:SUP-ALPHA", "inventory:SKU-SENSOR", "order:ORD-1001", "order:ORD-1002", "recovery:SUP-ALPHA",
    }
    assert all(item["source"].startswith("backend/app/data/demo_data.json#") for item in result["evidence"])


def test_repeated_simulations_do_not_mutate_stock_or_fixture() -> None:
    repository = FixtureRepository()
    original = repository.snapshot().model_dump_json()
    simulation_request = SimulationRequest(supplier_id="SUP-ALPHA", delay_days=5)
    first = simulate(simulation_request, repository).model_dump_json()
    second = simulate(simulation_request, repository).model_dump_json()
    assert first == second
    assert repository.snapshot().model_dump_json() == original


def test_order_priority_is_independent_of_source_array_order() -> None:
    data = FixtureRepository().snapshot()
    reversed_data = data.model_copy(update={"orders": list(reversed(data.orders))}, deep=True)
    simulation_request = SimulationRequest(supplier_id="SUP-BETA", delay_days=5)
    normal = simulate(simulation_request, StaticRepository(data))
    reversed_result = simulate(simulation_request, StaticRepository(reversed_data))
    assert normal == reversed_result


def test_recovery_cannot_arrive_before_original_restock() -> None:
    result = request("SUP-ALPHA", 1)
    expedite = next(item for item in result["recovery_options"] if item["strategy"] == "expedite_shipping")
    assert "Arrival 2026-10-27" in expedite["details"]


def test_repository_rejects_insufficient_replenishment(tmp_path: Path) -> None:
    data = FixtureRepository().snapshot().model_dump(mode="json")
    data["suppliers"][0]["replenishment_quantity"] = 1
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Insufficient scheduled replenishment"):
        FixtureRepository(path).snapshot()


def test_integrations_explicitly_refuse_to_fabricate_success() -> None:
    zetaris, meterless = ZetarisRepository(), MeterlessClient()
    assert zetaris.status().status == meterless.status().status == "not_configured"
    assert meterless.status().engine == meterless.status().nightshift == "not_configured"
    with pytest.raises(IntegrationNotConfigured):
        zetaris.snapshot()
    with pytest.raises(IntegrationNotConfigured):
        meterless.complete(prompt="Explain this evidence", model_id="unconfigured")


def test_development_cors_allows_frontend_origin() -> None:
    response = client.options("/api/simulations", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
