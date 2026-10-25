"""Deterministic FIFO allocation and hypothetical incremental recovery costs.

Money stays Decimal throughout. No model or external service calculates figures.
"""

from datetime import date, timedelta
from decimal import Decimal

from app.data.repository import DataRepository
from app.schemas import AffectedOrder, Evidence, RecoveryOption, SimulationRequest, SimulationResponse, Strategy


ZERO = Decimal("0.00")
DISCLAIMER = (
    "Synthetic fixture data and hypothetical costs only. Deterministic simulation; "
    "no Zetaris, Meterless Engine, Nightshift, NVIDIA inference, or autonomous agents are connected. "
    "No purchases, shipments, or customer orders are changed."
)


class UnknownSupplierError(ValueError):
    pass


def _penalty(order: AffectedOrder, delivery_date: date) -> Decimal:
    return order.penalty_per_day_gbp * max(0, (delivery_date - order.promised_date).days)


def simulate(request: SimulationRequest, repository: DataRepository) -> SimulationResponse:
    data = repository.snapshot()
    supplier = next((item for item in data.suppliers if item.supplier_id == request.supplier_id), None)
    if supplier is None:
        raise UnknownSupplierError(f"Unknown supplier: {request.supplier_id}")

    disrupted_date = supplier.restock_date + timedelta(days=request.delay_days)
    stock = next(item.on_hand_units for item in data.inventory if item.sku == supplier.sku)
    initial_stock = stock
    orders = sorted(
        (order for order in data.orders if order.supplier_id == supplier.supplier_id),
        key=lambda order: (order.promised_date, order.order_id),
    )
    allocated_orders: list[AffectedOrder] = []
    evidence = [
        Evidence(
            evidence_id=f"supplier:{supplier.supplier_id}",
            source=f"backend/app/data/demo_data.json#suppliers/{supplier.supplier_id}",
            description=(
                f"{supplier.name} supplies {supplier.sku}; scheduled replenishment "
                f"{supplier.replenishment_quantity} units on {supplier.restock_date}. "
                f"Injected delay {request.delay_days} calendar days moves arrival to {disrupted_date}."
            ),
        ),
        Evidence(
            evidence_id=f"inventory:{supplier.sku}",
            source=f"backend/app/data/demo_data.json#inventory/{supplier.sku}",
            description=(f"{initial_stock} on-hand units as of {data.as_of_date}; allocate by promised date, "
                         "then order ID. Full-order completion is required; warehouse-to-customer transit is zero days."),
        ),
    ]
    for order in orders:
        allocated = min(stock, order.quantity)
        stock -= allocated
        shortfall = order.quantity - allocated
        delivery = disrupted_date if shortfall else data.as_of_date
        late_days = max(0, (delivery - order.promised_date).days)
        penalty = order.penalty_per_day_gbp * late_days
        allocated_orders.append(AffectedOrder(
            **order.model_dump(), inventory_allocated=allocated, shortfall_units=shortfall,
            expected_delivery_date=delivery, delay_days=late_days, estimated_penalty_gbp=penalty,
        ))
        evidence.append(Evidence(
            evidence_id=f"order:{order.order_id}",
            source=f"backend/app/data/demo_data.json#orders/{order.order_id}",
            description=(
                f"{order.order_id}: {order.quantity} units due {order.promised_date}; "
                f"stock allocation {allocated}, shortfall {shortfall}; complete {delivery}; "
                f"{late_days} days late × GBP {order.penalty_per_day_gbp:.2f}/order/day "
                f"= GBP {penalty:.2f}. Penalty applies to the whole order, not each unit."
            ),
        ))

    exposure = sum((order.estimated_penalty_gbp for order in allocated_orders), ZERO)
    recovery_options = [RecoveryOption(
        strategy="accept_delay", residual_penalty_gbp=exposure, action_cost_gbp=ZERO,
        total_estimated_cost_gbp=exposure, saving_vs_no_action_gbp=ZERO,
        details=(f"Take no action. Uncovered units complete on {disrupted_date}; "
                 f"estimated late-order penalties GBP {exposure:.2f}."),
    )]

    def intervention(
        strategy: Strategy, arrival: date, capacity: int, fixed_fee: Decimal,
        unit_fee: Decimal, explanation: str,
    ) -> RecoveryOption:
        remaining = capacity
        units_used = 0
        residual = ZERO
        allocation_details = []
        for order in allocated_orders:
            can_help = order.delay_days > 0 and order.shortfall_units > 0 and arrival < order.expected_delivery_date
            recovered = min(remaining, order.shortfall_units) if can_help else 0
            remaining -= recovered
            units_used += recovered
            # Partial intervention stock cannot complete an order before its last units arrive.
            delivery = arrival if recovered and recovered == order.shortfall_units else order.expected_delivery_date
            residual += _penalty(order, delivery)
            if recovered:
                allocation_details.append(f"{order.order_id}: {recovered}/{order.shortfall_units} shortfall units, complete {delivery}")
        action_cost = fixed_fee + unit_fee * units_used if units_used else ZERO
        total = residual + action_cost
        return RecoveryOption(
            strategy=strategy, residual_penalty_gbp=residual, action_cost_gbp=action_cost,
            total_estimated_cost_gbp=total, saving_vs_no_action_gbp=exposure-total,
            details=(
                f"{explanation} Arrival {arrival}; capacity {capacity} units; allocated {units_used}. "
                f"Fee when used = GBP {fixed_fee:.2f} + GBP {unit_fee:.2f}/unit. "
                f"{' ; '.join(allocation_details) if allocation_details else 'No earlier recovery needed or possible; no action fee charged'}. "
                "Capacity follows promised-date/order-ID priority; partial orders wait for their remaining regular stock."
            ),
        )

    expedite = supplier.expedite
    expedite_arrival = max(supplier.restock_date, disrupted_date-timedelta(days=expedite.days_saved))
    recovery_options.append(intervention(
        "expedite_shipping", expedite_arrival, expedite.capacity_units,
        expedite.fixed_fee_gbp, expedite.per_unit_fee_gbp,
        f"Expedite can recover up to {expedite.days_saved} injected-delay days, never before the original restock date.",
    ))
    alternative = supplier.alternative
    recovery_options.append(intervention(
        "alternative_supplier", data.as_of_date+timedelta(days=alternative.lead_time_days),
        alternative.capacity_units, alternative.fixed_fee_gbp, alternative.unit_premium_gbp,
        f"Use {alternative.supplier_name}, lead time {alternative.lead_time_days} days from evaluation.",
    ))
    # Python's stable sort preserves accept/expedite/alternative order when total costs tie.
    recovery_options.sort(key=lambda option: option.total_estimated_cost_gbp)
    evidence.append(Evidence(
        evidence_id=f"recovery:{supplier.supplier_id}",
        source=f"backend/app/data/demo_data.json#suppliers/{supplier.supplier_id}",
        description=(
            f"Expedite: {expedite.days_saved} days saved, {expedite.capacity_units} units, "
            f"GBP {expedite.fixed_fee_gbp:.2f} + {expedite.per_unit_fee_gbp:.2f}/unit. "
            f"Alternative: {alternative.lead_time_days} days, {alternative.capacity_units} units, "
            f"GBP {alternative.fixed_fee_gbp:.2f} + {alternative.unit_premium_gbp:.2f}/unit. "
            "Costs are incremental fees plus residual penalties; common base procurement, taxes, "
            "weekends, cancellation, split-delivery benefits, and transit are excluded. "
            "Unused regular/alternative units have no modeled charge. Recovery fees are hypothetical."
        ),
    ))
    return SimulationResponse(
        supplier_id=supplier.supplier_id, delay_days=request.delay_days, as_of_date=data.as_of_date,
        disrupted_restock_date=disrupted_date,
        affected_orders=[order for order in allocated_orders if order.delay_days > 0],
        estimated_penalty_exposure_gbp=exposure, recovery_options=recovery_options,
        recommended_strategy=recovery_options[0].strategy, evidence=evidence, disclaimer=DISCLAIMER,
    )
