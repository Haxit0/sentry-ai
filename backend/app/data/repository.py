"""Read-only repository boundary; future Zetaris data must map to these types."""

from pathlib import Path
from typing import Protocol

from app.schemas import DemoData


class DataRepository(Protocol):
    def snapshot(self) -> DemoData:
        """Return a validated, isolated snapshot including provenance dates."""
        ...


class FixtureRepository:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Path(__file__).with_name("demo_data.json")

    def snapshot(self) -> DemoData:
        data = DemoData.model_validate_json(self._path.read_text(encoding="utf-8"))
        supplier_ids = {item.supplier_id for item in data.suppliers}
        skus = {item.sku for item in data.suppliers}
        if len(supplier_ids) != len(data.suppliers) or len(skus) != len(data.suppliers):
            raise ValueError("Fixture requires unique supplier IDs and one supplier per SKU")
        if len({item.order_id for item in data.orders}) != len(data.orders):
            raise ValueError("Duplicate order IDs in fixture")
        if len({item.sku for item in data.inventory}) != len(data.inventory):
            raise ValueError("Duplicate inventory SKU in fixture")
        stock = {item.sku: item.on_hand_units for item in data.inventory}
        suppliers = {item.supplier_id: item for item in data.suppliers}
        for order in data.orders:
            if order.supplier_id not in suppliers or order.sku != suppliers[order.supplier_id].sku:
                raise ValueError(f"Invalid supplier/SKU relationship: {order.order_id}")
        for supplier in data.suppliers:
            if supplier.sku not in stock or supplier.restock_date < data.as_of_date:
                raise ValueError(f"Missing inventory or past replenishment: {supplier.supplier_id}")
            demand = sum(order.quantity for order in data.orders if order.supplier_id == supplier.supplier_id)
            if demand > stock[supplier.sku] + supplier.replenishment_quantity:
                raise ValueError(f"Insufficient scheduled replenishment: {supplier.supplier_id}")
        return data
