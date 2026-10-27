"""Zetaris client and repository against mocked HTTP. No network; see test_zetaris_live.py for the real thing."""

import json
import uuid
from decimal import Decimal

import httpx
import pytest

from app.data.repository import FixtureRepository
from app.data.zetaris_repository import ZetarisRepository, federated_orders_sql
from app.integrations.zetaris import (
    IntegrationNotConfigured,
    ZetarisAuthError,
    ZetarisClient,
    ZetarisConfig,
    ZetarisDataError,
    ZetarisQueryError,
    ZetarisUnavailable,
    identifier,
)
from app.schemas import DemoData, SimulationRequest
from app.services.simulation import simulate
from scripts.zetaris_dataset import main as dataset_main

TOKEN = "test-token-not-real"
CONFIG = ZetarisConfig(base_url="http://zetaris.test/api/v1.0", api_token=TOKEN, org_id="7", max_rows=50)
FIXTURE = FixtureRepository().snapshot()


def tables(data: DemoData = FIXTURE) -> dict[str, dict]:
    """What the real platform returns for the three repository queries (every cell is a string)."""
    suppliers = [[
        s.supplier_id, s.name, s.sku, s.restock_date.isoformat(), str(s.replenishment_quantity),
        str(s.expedite.days_saved), str(s.expedite.capacity_units),
        f"{s.expedite.fixed_fee_gbp:.2f}", f"{s.expedite.per_unit_fee_gbp:.2f}",
        s.alternative.supplier_name, str(s.alternative.lead_time_days), str(s.alternative.capacity_units),
        f"{s.alternative.fixed_fee_gbp:.2f}", f"{s.alternative.unit_premium_gbp:.2f}",
    ] for s in data.suppliers]
    sku_of = {s.supplier_id: s.sku for s in data.suppliers}
    orders = [[  # PostgreSQL numeric(14,2) comes back through Zetaris as decimal(38,18) text
        o.order_id, o.customer_name, o.supplier_id, o.sku, str(o.quantity), o.promised_date.isoformat(),
        f"{o.penalty_per_day_gbp:.18f}", sku_of.get(o.supplier_id),
    ] for o in data.orders]
    return {
        "suppliers": {"headers": [
            "supplier_id", "name", "sku", "restock_date", "replenishment_quantity", "expedite_days_saved",
            "expedite_capacity_units", "expedite_fixed_fee_gbp", "expedite_per_unit_fee_gbp",
            "alternative_supplier_name", "alternative_lead_time_days", "alternative_capacity_units",
            "alternative_fixed_fee_gbp", "alternative_unit_premium_gbp"], "data": suppliers},
        "inventory": {"headers": ["sku", "on_hand_units"], "data": [[i.sku, str(i.on_hand_units)] for i in data.inventory]},
        "orders": {"headers": ["order_id", "customer_name", "supplier_id", "sku", "quantity", "promised_date",
                               "penalty_per_day_gbp", "supplier_sku"], "data": orders},
    }


class FakeZetaris:
    """httpx transport that answers like /sql-editor/sqls/run and records each request."""

    def __init__(self, payloads: dict[str, dict] | None = None) -> None:
        self.payloads = payloads or tables()
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        sql = json.loads(request.content)["sql"]
        if "JOIN" in sql:
            key = "orders"
        elif "SENTRY_SUPPLIER_PORTAL.suppliers" in sql:
            key = "suppliers"
        elif "SENTRY_SUPPLIER_PORTAL.inventory" in sql:
            key = "inventory"
        else:
            return httpx.Response(200, json={"headers": ["seven"], "data": [["7"]], "total": 1, "timeUsed": 3})
        payload = self.payloads[key]
        return httpx.Response(200, json={**payload, "total": len(payload["data"]), "timeUsed": 12})

    def repository(self) -> ZetarisRepository:
        return ZetarisRepository(CONFIG, transport=httpx.MockTransport(self))


def failing(response: httpx.Response | Exception) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(response, Exception):
            raise response
        return response
    return httpx.MockTransport(handler)


# 1. Authenticated SQL request

def test_query_sends_authenticated_bounded_request_with_fresh_ids() -> None:
    fake = FakeZetaris()
    with ZetarisClient(CONFIG, transport=httpx.MockTransport(fake)) as client:
        first = client.query("select 7 as seven")
        client.query("select 7 as seven")
    assert first.headers == ("seven",) and first.rows == ({"seven": "7"},) and first.time_used_ms == 3
    one, two = fake.requests
    assert one.url == "http://zetaris.test/api/v1.0/sql-editor/sqls/run"
    assert one.headers["Authorization"] == f"Bearer {TOKEN}"
    assert one.headers["X-Org-ID"] == "7"
    body = json.loads(one.content)
    assert body == {"queryId": body["queryId"], "sql": "select 7 as seven", "source": "Generic", "limit": 51}
    uuid.UUID(body["queryId"]), uuid.UUID(one.headers["X-Request-ID"])
    assert one.headers["X-Request-ID"] != two.headers["X-Request-ID"]
    assert body["queryId"] != json.loads(two.content)["queryId"]


def test_configuration_comes_from_environment_and_hides_token() -> None:
    config = ZetarisConfig.from_env({
        "ZETARIS_BASE_URL": "http://h/api/v1.0/", "ZETARIS_API_TOKEN": TOKEN, "ZETARIS_ORG_ID": "1",
        "ZETARIS_READ_TIMEOUT_SECONDS": "9",
    })
    assert (config.base_url, config.org_id, config.read_timeout, config.connect_timeout) == ("http://h/api/v1.0", "1", 9.0, 5.0)
    assert TOKEN not in repr(config)
    with pytest.raises(IntegrationNotConfigured, match="ZETARIS_API_TOKEN"):
        ZetarisConfig.from_env({"ZETARIS_BASE_URL": "http://h", "ZETARIS_ORG_ID": "1"})
    with pytest.raises(IntegrationNotConfigured, match="numeric"):
        ZetarisConfig.from_env({"ZETARIS_BASE_URL": "http://h", "ZETARIS_API_TOKEN": TOKEN, "ZETARIS_ORG_ID": "org"})


def test_unconfigured_repository_never_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZETARIS_BASE_URL", "http://h")
    monkeypatch.setenv("ZETARIS_API_TOKEN", TOKEN)
    monkeypatch.setenv("ZETARIS_ORG_ID", "1")
    repository = ZetarisRepository()
    assert repository.status().status == "not_configured"
    with pytest.raises(IntegrationNotConfigured):
        repository.snapshot()
    assert ZetarisRepository.from_env().status().status == "configured"


# 2. Mapping to the shared Pydantic types

def test_snapshot_maps_zetaris_rows_to_identical_validated_demo_data() -> None:
    fake = FakeZetaris()
    data = fake.repository().snapshot()
    assert data == FIXTURE
    order = next(o for o in data.orders if o.order_id == "ORD-1002")
    assert order.penalty_per_day_gbp == Decimal("100.00") and str(order.penalty_per_day_gbp) == "100.00"
    assert [json.loads(r.content)["sql"] for r in fake.requests][-1] == federated_orders_sql()


def test_orders_are_read_through_one_cross_source_join() -> None:
    sql = federated_orders_sql()
    assert "FROM SENTRY_ERP_PG.customer_orders o LEFT JOIN SENTRY_SUPPLIER_PORTAL.suppliers s" in sql


# 3. Missing suppliers or orders

def test_order_whose_supplier_is_missing_from_the_other_source_is_rejected() -> None:
    payloads = tables()
    payloads["orders"]["data"][0][-1] = None  # LEFT JOIN found no supplier row
    with pytest.raises(ZetarisDataError, match="ORD-1001: supplier SUP-ALPHA not found in SENTRY_SUPPLIER_PORTAL.suppliers"):
        FakeZetaris(payloads).repository().snapshot()


def test_supplier_without_inventory_is_rejected() -> None:
    payloads = tables()
    payloads["inventory"]["data"] = payloads["inventory"]["data"][1:]
    with pytest.raises(ZetarisDataError, match="Missing inventory or past replenishment: SUP-ALPHA"):
        FakeZetaris(payloads).repository().snapshot()


def test_empty_orders_are_rejected_not_treated_as_no_impact() -> None:
    payloads = tables()
    payloads["orders"]["data"] = []
    with pytest.raises(ZetarisDataError, match="Missing suppliers, orders or inventory"):
        FakeZetaris(payloads).repository().snapshot()


def test_mismatched_sku_across_sources_is_rejected() -> None:
    payloads = tables()
    payloads["orders"]["data"][0][3] = "SKU-CASING"
    with pytest.raises(ZetarisDataError, match="does not match supplier SUP-ALPHA"):
        FakeZetaris(payloads).repository().snapshot()


# 4. Malformed data

@pytest.mark.parametrize(("table", "row", "column", "value", "message"), [
    ("orders", 0, 5, "2026-13-01", "promised_date is not an ISO date"),
    ("orders", 0, 5, "26/10/2026", "promised_date is not an ISO date"),
    ("orders", 0, 6, "12.345000000000000000", "not a whole-penny amount"),
    ("orders", 0, 6, "NaN", "not a whole-penny amount"),
    ("orders", 0, 6, "fifty", "not a decimal amount"),
    ("orders", 0, 4, "1.5", "quantity is not an integer"),
    ("orders", 0, 4, "0", "quantity: Input should be greater than 0"),
    ("orders", 0, 1, None, "missing customer_name"),
    ("suppliers", 0, 7, "-1.00", "fixed_fee_gbp: Input should be greater than or equal to 0"),
    ("inventory", 0, 1, "-3", "on_hand_units: Input should be greater than or equal to 0"),
])
def test_malformed_values_are_rejected_with_record_context(table, row, column, value, message) -> None:
    payloads = tables()
    payloads[table]["data"][row][column] = value
    with pytest.raises(ZetarisDataError, match=message):
        FakeZetaris(payloads).repository().snapshot()


def test_duplicate_records_are_rejected() -> None:
    payloads = tables()
    payloads["orders"]["data"].append(list(payloads["orders"]["data"][0]))
    with pytest.raises(ZetarisDataError, match="Duplicate order IDs in Zetaris snapshot"):
        FakeZetaris(payloads).repository().snapshot()


def test_unexpected_columns_or_row_shapes_are_rejected() -> None:
    payloads = tables()
    payloads["inventory"]["headers"] = ["sku", "qty"]
    with pytest.raises(ZetarisDataError, match="Unexpected columns"):
        FakeZetaris(payloads).repository().snapshot()
    payloads = tables()
    payloads["inventory"]["data"][0] = ["SKU-SENSOR"]
    with pytest.raises(ZetarisQueryError, match="Malformed Zetaris row 0"):
        FakeZetaris(payloads).repository().snapshot()
    client = ZetarisClient(CONFIG, transport=failing(httpx.Response(200, json={"rows": []})))
    with pytest.raises(ZetarisQueryError, match="Unexpected Zetaris response shape"):
        client.query("select 1 as one")


def test_oversized_results_are_refused_rather_than_truncated() -> None:
    payload = {"headers": ["n"], "data": [[str(i)] for i in range(51)]}
    client = ZetarisClient(CONFIG, transport=failing(httpx.Response(200, json=payload)))
    with pytest.raises(ZetarisDataError, match="more than 50 rows"):
        client.query("select n from t")


# 5-7. Authentication, availability and timeouts: always raise, never fall back

@pytest.mark.parametrize(("status", "body"), [
    (400, {"msg": "Not Allowed"}),  # what Zetaris 2.4 actually returns for a bad key or org id
    (400, "Not Allowed"),
    (401, "Invalid value for: header Authorization"),
    (403, "Forbidden"),
])
def test_rejected_credentials_raise_auth_error_without_leaking_token(status: int, body) -> None:
    response = httpx.Response(status, json=body) if isinstance(body, dict) else httpx.Response(status, text=body)
    repository = ZetarisRepository(CONFIG, transport=failing(response))
    with pytest.raises(ZetarisAuthError, match=f"HTTP {status}") as error:
        repository.snapshot()
    assert TOKEN not in str(error.value)


@pytest.mark.parametrize("failure", [
    httpx.ConnectError("connection refused"),
    httpx.Response(503, text="Service Unavailable"),
    httpx.Response(500, json={"msg": "driver is starting\n\tat com.zetaris.Foo(Foo.scala:1)"}),
])
def test_unavailable_platform_raises_and_returns_no_records(failure) -> None:
    repository = ZetarisRepository(CONFIG, transport=failing(failure))
    with pytest.raises(ZetarisUnavailable) as error:
        repository.snapshot()
    assert "\tat " not in str(error.value)
    assert repository.last_queries == ()


@pytest.mark.parametrize("timeout", [httpx.ConnectTimeout("slow connect"), httpx.ReadTimeout("slow query")])
def test_timeouts_raise_unavailable(timeout: Exception) -> None:
    with pytest.raises(ZetarisUnavailable, match="timed out"):
        ZetarisRepository(CONFIG, transport=failing(timeout)).snapshot()


def test_client_uses_configured_connect_and_read_timeouts() -> None:
    client = ZetarisClient(ZetarisConfig(base_url="http://h", api_token=TOKEN, org_id="1", connect_timeout=2, read_timeout=30))
    assert (client._http.timeout.connect, client._http.timeout.read) == (2, 30)


def test_rejected_sql_surfaces_the_zetaris_message() -> None:
    client = ZetarisClient(CONFIG, transport=failing(httpx.Response(400, json={"msg": "[TABLE_OR_VIEW_NOT_FOUND] nope"})))
    with pytest.raises(ZetarisQueryError, match=r"HTTP 400\): \[TABLE_OR_VIEW_NOT_FOUND\] nope"):
        client.query("select a from b")


# 8. SQL safety

@pytest.mark.parametrize("name", ["orders; DROP TABLE x", "a.b", "1abc", "", "o'r", "x--", "a b", "ä", "x" * 65])
def test_unsafe_identifiers_are_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        identifier(name)


def test_select_validates_identifiers_before_any_network_call() -> None:
    fake = FakeZetaris()
    with ZetarisClient(CONFIG, transport=httpx.MockTransport(fake)) as client:
        with pytest.raises(ValueError):
            client.select(("SENTRY_ERP_PG", "orders; DROP DATASOURCE x"), ["order_id"], ["order_id"])
        with pytest.raises(ValueError):
            client.select(("SENTRY_ERP_PG", "customer_orders"), ["order_id) UNION SELECT (1"], ["order_id"])
    assert fake.requests == []


@pytest.mark.parametrize("sql", [
    "DROP DATASOURCE SENTRY_ERP_PG",
    "select 1; drop table x",
    "REGISTER DATASOURCE TABLES FROM SENTRY_ERP_PG",
    "select * from (insert into t values (1))",
    "with x as (select 1) select * from x",
    "CREATE LIGHTNING DATABASE X OPTIONS ()",
])
def test_read_only_path_refuses_anything_but_one_select(sql: str) -> None:
    fake = FakeZetaris()
    with ZetarisClient(CONFIG, transport=httpx.MockTransport(fake)) as client:
        with pytest.raises(ValueError, match="read-only SELECT"):
            client.query(sql)
    assert fake.requests == []


# 9. Provenance

def test_live_evidence_cites_zetaris_sources_and_never_the_fixture() -> None:
    repository = FakeZetaris().repository()
    result = simulate(SimulationRequest(supplier_id="SUP-ALPHA", delay_days=5), repository)
    sources = {item.evidence_id: item.source for item in result.evidence}
    assert sources["supplier:SUP-ALPHA"] == "zetaris://SENTRY_SUPPLIER_PORTAL.suppliers/SUP-ALPHA"
    assert sources["inventory:SKU-SENSOR"] == "zetaris://SENTRY_SUPPLIER_PORTAL.inventory/SKU-SENSOR"
    assert sources["order:ORD-1002"] == "zetaris://SENTRY_ERP_PG.customer_orders/ORD-1002"
    assert not any("demo_data.json" in source for source in sources.values())
    assert [q.sources for q in repository.last_queries] == [
        ("SENTRY_SUPPLIER_PORTAL.suppliers",), ("SENTRY_SUPPLIER_PORTAL.inventory",),
        ("SENTRY_ERP_PG.customer_orders", "SENTRY_SUPPLIER_PORTAL.suppliers"),
    ]
    assert all(uuid.UUID(q.query_id) and q.time_used_ms == 12 for q in repository.last_queries)


def test_fixture_evidence_is_unchanged() -> None:
    result = simulate(SimulationRequest(supplier_id="SUP-ALPHA", delay_days=5), FixtureRepository())
    assert {item.source for item in result.evidence} == {
        "backend/app/data/demo_data.json#suppliers/SUP-ALPHA", "backend/app/data/demo_data.json#inventory/SKU-SENSOR",
        "backend/app/data/demo_data.json#orders/ORD-1001", "backend/app/data/demo_data.json#orders/ORD-1002",
    }


# 10. Deterministic simulator compatibility

@pytest.mark.parametrize("supplier_id", ["SUP-ALPHA", "SUP-BETA", "SUP-GAMMA"])
@pytest.mark.parametrize("delay_days", [0, 1, 5, 30])
def test_simulation_over_zetaris_data_matches_fixture_figures(supplier_id: str, delay_days: int) -> None:
    request = SimulationRequest(supplier_id=supplier_id, delay_days=delay_days)
    live = simulate(request, FakeZetaris().repository()).model_dump(exclude={"evidence"})
    fixture = simulate(request, FixtureRepository()).model_dump(exclude={"evidence"})
    assert live == fixture


def test_alpha_five_day_golden_answer_from_zetaris_rows() -> None:
    result = simulate(SimulationRequest(supplier_id="SUP-ALPHA", delay_days=5), FakeZetaris().repository())
    assert result.estimated_penalty_exposure_gbp == Decimal("500.00")
    assert (result.recommended_strategy, result.recovery_options[0].total_estimated_cost_gbp) == ("expedite_shipping", Decimal("160.00"))


def test_committed_zetaris_dataset_matches_fixture() -> None:
    assert dataset_main(["--check"]) == 0
