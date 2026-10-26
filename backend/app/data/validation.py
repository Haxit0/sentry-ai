"""Snapshot rules shared by every repository, so fixture and Zetaris data meet the same bar."""

from app.schemas import DemoData


def validate_snapshot(data: DemoData, source: str = "fixture") -> DemoData:
    """Raise ValueError naming `source` if identifiers or relationships are inconsistent."""
    if not data.suppliers or not data.orders or not data.inventory:
        raise ValueError(f"Missing suppliers, orders or inventory in {source}")
    supplier_ids = {item.supplier_id for item in data.suppliers}
    skus = {item.sku for item in data.suppliers}
    if len(supplier_ids) != len(data.suppliers) or len(skus) != len(data.suppliers):
        raise ValueError(f"{source.capitalize()} requires unique supplier IDs and one supplier per SKU")
    if len({item.order_id for item in data.orders}) != len(data.orders):
        raise ValueError(f"Duplicate order IDs in {source}")
    if len({item.sku for item in data.inventory}) != len(data.inventory):
        raise ValueError(f"Duplicate inventory SKU in {source}")
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
