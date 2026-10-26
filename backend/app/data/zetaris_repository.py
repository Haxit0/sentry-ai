"""DataRepository over live Zetaris queries.

Two independent sources, federated by Zetaris:
- SENTRY_ERP_PG          JDBC datasource over PostgreSQL: customer_orders
- SENTRY_SUPPLIER_PORTAL Lightning filestore database over CSV: suppliers, inventory

Orders are read through one cross-source join so an order whose supplier is missing from the
supplier portal is caught in Zetaris, not silently dropped. Failures raise; there is no fixture
fallback. See docs/ZETARIS_INTEGRATION.md.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from pydantic import ValidationError

from app.data.validation import validate_snapshot
from app.integrations.zetaris import (
    IntegrationNotConfigured,
    IntegrationStatus,
    QueryResult,
    ZetarisClient,
    ZetarisConfig,
    ZetarisDataError,
    identifier,
)
from app.schemas import DemoData, Inventory, Order, Supplier

EVALUATION_DATE = date(2026, 10, 25)
ERP_SOURCE = "SENTRY_ERP_PG"
PORTAL_SOURCE = "SENTRY_SUPPLIER_PORTAL"
ORDERS_TABLE = (ERP_SOURCE, "customer_orders")
SUPPLIERS_TABLE = (PORTAL_SOURCE, "suppliers")
INVENTORY_TABLE = (PORTAL_SOURCE, "inventory")

SUPPLIER_COLUMNS = (
    "supplier_id", "name", "sku", "restock_date", "replenishment_quantity",
    "expedite_days_saved", "expedite_capacity_units", "expedite_fixed_fee_gbp", "expedite_per_unit_fee_gbp",
    "alternative_supplier_name", "alternative_lead_time_days", "alternative_capacity_units",
    "alternative_fixed_fee_gbp", "alternative_unit_premium_gbp",
)
ORDER_COLUMNS = ("order_id", "customer_name", "supplier_id", "sku", "quantity", "promised_date", "penalty_per_day_gbp")
INVENTORY_COLUMNS = ("sku", "on_hand_units")

_EVIDENCE_TABLES = {"suppliers": SUPPLIERS_TABLE, "inventory": INVENTORY_TABLE, "orders": ORDERS_TABLE}
_INTEGER = re.compile(r"-?\d+")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_PENNY = Decimal("0.01")


def federated_orders_sql() -> str:
    """Orders from PostgreSQL joined to the CSV supplier portal, in one Zetaris statement."""
    orders, suppliers = (".".join(identifier(part) for part in table) for table in (ORDERS_TABLE, SUPPLIERS_TABLE))
    columns = ", ".join(f"o.{identifier(column)}" for column in ORDER_COLUMNS)
    return (
        f"SELECT {columns}, s.sku AS supplier_sku FROM {orders} o "
        f"LEFT JOIN {suppliers} s ON o.supplier_id = s.supplier_id ORDER BY o.order_id"
    )


@dataclass(frozen=True)
class QueryProvenance:
    sources: tuple[str, ...]
    query_id: str
    rows: int
    time_used_ms: int | None


class ZetarisRepository:
    def __init__(
        self, config: ZetarisConfig | None = None, *,
        transport: httpx.BaseTransport | None = None, as_of_date: date = EVALUATION_DATE,
    ) -> None:
        # Never reads the environment implicitly: Zetaris mode is an explicit choice (see from_env).
        self._config = config
        self._transport = transport
        self._as_of_date = as_of_date
        self.last_queries: tuple[QueryProvenance, ...] = ()

    @classmethod
    def from_env(cls, **kwargs: Any) -> "ZetarisRepository":
        return cls(ZetarisConfig.from_env(), **kwargs)

    def status(self) -> IntegrationStatus:
        if self._config is None:
            return IntegrationStatus()
        return IntegrationStatus("configured", "Settings present; only a successful snapshot() proves Zetaris is reachable.")

    def evidence_source(self, collection: str, record_id: str) -> str:
        source, table = _EVIDENCE_TABLES[collection]
        return f"zetaris://{source}.{table}/{record_id}"

    def snapshot(self) -> DemoData:
        if self._config is None:
            raise IntegrationNotConfigured(self.status().reason)
        with ZetarisClient(self._config, transport=self._transport) as client:
            supplier_result = client.select(SUPPLIERS_TABLE, SUPPLIER_COLUMNS, ("supplier_id",))
            inventory_result = client.select(INVENTORY_TABLE, INVENTORY_COLUMNS, ("sku",))
            order_result = client.query(federated_orders_sql())
        self.last_queries = (
            _provenance(supplier_result, SUPPLIERS_TABLE),
            _provenance(inventory_result, INVENTORY_TABLE),
            _provenance(order_result, ORDERS_TABLE, SUPPLIERS_TABLE),
        )
        data = DemoData(
            as_of_date=self._as_of_date,
            suppliers=[_supplier(row) for row in _rows(supplier_result, SUPPLIER_COLUMNS)],
            inventory=[_inventory(row) for row in _rows(inventory_result, INVENTORY_COLUMNS)],
            orders=[_order(row) for row in _rows(order_result, (*ORDER_COLUMNS, "supplier_sku"))],
        )
        try:
            return validate_snapshot(data, source="Zetaris snapshot")
        except ValueError as exc:
            raise ZetarisDataError(str(exc)) from exc


def _provenance(result: QueryResult, *tables: tuple[str, str]) -> QueryProvenance:
    return QueryProvenance(tuple(".".join(table) for table in tables), result.query_id, len(result.rows), result.time_used_ms)


def _rows(result: QueryResult, expected: tuple[str, ...]) -> tuple[dict[str, str | None], ...]:
    if result.headers != expected:
        raise ZetarisDataError(f"Unexpected columns {list(result.headers)}; expected {list(expected)}")
    return result.rows


def _cell(row: dict[str, str | None], column: str, record: str) -> str:
    value = row[column]
    if value is None or not value.strip():
        raise ZetarisDataError(f"{record}: missing {column}")
    return value.strip()


def _int(row: dict[str, str | None], column: str, record: str) -> int:
    value = _cell(row, column, record)
    if not _INTEGER.fullmatch(value):
        raise ZetarisDataError(f"{record}: {column} is not an integer: {value!r}")
    return int(value)


def _date(row: dict[str, str | None], column: str, record: str) -> date:
    value = _cell(row, column, record)
    try:
        if not _ISO_DATE.fullmatch(value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise ZetarisDataError(f"{record}: {column} is not an ISO date: {value!r}") from None


def _money(row: dict[str, str | None], column: str, record: str) -> Decimal:
    # PostgreSQL numeric(14,2) arrives as decimal(38,18) text; accept only whole pennies, never round.
    value = _cell(row, column, record)
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise ZetarisDataError(f"{record}: {column} is not a decimal amount: {value!r}") from None
    if not amount.is_finite() or amount != amount.quantize(_PENNY):
        raise ZetarisDataError(f"{record}: {column} is not a whole-penny amount: {value!r}")
    return amount.quantize(_PENNY)


def _build(model: type, record: str, **fields: Any) -> Any:
    try:
        return model(**fields)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in exc.errors())
        raise ZetarisDataError(f"{record}: {problems}") from None


def _supplier(row: dict[str, str | None]) -> Supplier:
    record = f"{SUPPLIERS_TABLE[0]}.{SUPPLIERS_TABLE[1]}/{row.get('supplier_id')}"
    return _build(
        Supplier, record,
        supplier_id=_cell(row, "supplier_id", record), name=_cell(row, "name", record), sku=_cell(row, "sku", record),
        restock_date=_date(row, "restock_date", record),
        replenishment_quantity=_int(row, "replenishment_quantity", record),
        expedite={
            "days_saved": _int(row, "expedite_days_saved", record),
            "capacity_units": _int(row, "expedite_capacity_units", record),
            "fixed_fee_gbp": _money(row, "expedite_fixed_fee_gbp", record),
            "per_unit_fee_gbp": _money(row, "expedite_per_unit_fee_gbp", record),
        },
        alternative={
            "supplier_name": _cell(row, "alternative_supplier_name", record),
            "lead_time_days": _int(row, "alternative_lead_time_days", record),
            "capacity_units": _int(row, "alternative_capacity_units", record),
            "fixed_fee_gbp": _money(row, "alternative_fixed_fee_gbp", record),
            "unit_premium_gbp": _money(row, "alternative_unit_premium_gbp", record),
        },
    )


def _inventory(row: dict[str, str | None]) -> Inventory:
    record = f"{INVENTORY_TABLE[0]}.{INVENTORY_TABLE[1]}/{row.get('sku')}"
    return _build(Inventory, record, sku=_cell(row, "sku", record), on_hand_units=_int(row, "on_hand_units", record))


def _order(row: dict[str, str | None]) -> Order:
    record = f"{ORDERS_TABLE[0]}.{ORDERS_TABLE[1]}/{row.get('order_id')}"
    supplier_id, sku = _cell(row, "supplier_id", record), _cell(row, "sku", record)
    if row["supplier_sku"] is None:
        raise ZetarisDataError(f"{record}: supplier {supplier_id} not found in {PORTAL_SOURCE}.suppliers")
    if row["supplier_sku"].strip() != sku:
        raise ZetarisDataError(f"{record}: SKU {sku} does not match supplier {supplier_id} SKU {row['supplier_sku']}")
    return _build(
        Order, record,
        order_id=_cell(row, "order_id", record), customer_name=_cell(row, "customer_name", record),
        supplier_id=supplier_id, sku=sku, quantity=_int(row, "quantity", record),
        promised_date=_date(row, "promised_date", record),
        penalty_per_day_gbp=_money(row, "penalty_per_day_gbp", record),
    )
