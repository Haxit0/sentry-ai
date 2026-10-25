# Architecture and calculation assumptions

## Current working system

The baseline is a deterministic supply-chain simulator over synthetic JSON. It makes no external integration calls and executes no real recovery action.

```text
frontend/src/App.tsx
  GET health/suppliers/orders; POST simulation
                 ↓ /api (Vite proxy, port 5173 → 8000)
backend/app/main.py              HTTP validation and typed responses
                 ↓
backend/app/services/simulation.py    exact Decimal calculations
                 ↓ DataRepository.snapshot()
backend/app/data/repository.py         validated independent snapshot
                 ↓
backend/app/data/demo_data.json        fixed synthetic fixture
```

`backend/app/schemas.py` defines the frozen shared types. `docs/CONTRACT.md` describes JSON serialization and meaning. API docs at `/docs` and OpenAPI at `/openapi.json` are generated from those types.

## Fixture and repository boundary

The fixture contains three primary suppliers, one unique SKU per supplier, six single-SKU customer orders, inventory for three SKUs, scheduled replenishments, and separate alternative supplier offers. The evaluation date is always **2026-10-25**.

`FixtureRepository.snapshot()` parses and validates records on each call, verifies unique identifiers, order/supplier/SKU relationships, stock presence, future replenishments and sufficient total scheduled supply. Each simulation gets an independent snapshot; requests do not consume global inventory. A future Zetaris repository implements the same typed `snapshot()` boundary. It must retain validation and real source provenance.

## Deterministic calculation

For the selected supplier only:

1. Add the requested 0–30 calendar-day delay to the scheduled restock date.
2. Sort orders by `(promised_date, order_id)` for stable earliest-date allocation.
3. Allocate available on-hand units to each order. `shortfall = quantity − inventory_allocated`.
4. A fully stocked order completes on the evaluation date. Any remaining shortfall makes the entire order complete on the disrupted restock date.
5. `late_days = max(0, expected_delivery_date − promised_date)` in calendar days.
6. `penalty = late_days × penalty_per_day_gbp`; this is a flat daily fee for the entire order, not per unit.
7. Sum penalties for no-action exposure. Return only late orders in `affected_orders`; evidence also explains on-time inventory allocations.

Money remains Python `Decimal`, loaded from decimal strings; JSON money is always a two-decimal string. No LLM or binary floating-point arithmetic calculates finances.

## Recovery policies

Each policy reuses the same initial warehouse allocation. Capacity is an available offer per simulated scenario, not a shared mutable balance.

| Policy | Arrival | Incremental action cost |
| --- | --- | --- |
| `accept_delay` | Disrupted restock | £0 |
| `expedite_shipping` | Later of original restock and disrupted restock minus configured `days_saved` | Fixed fee plus per-unit fee for allocated intervention units |
| `alternative_supplier` | Evaluation date plus configured lead time | Fixed fee plus premium per allocated unit |

Intervention capacity goes to late orders in the same promised-date/order-ID priority. Units are allocated only when the intervention can arrive earlier than that order's no-action completion. A fully covered shortfall completes on intervention arrival. A partially covered order still waits for its remaining regular stock and receives no earlier whole-order penalty benefit. Fixed fees apply once only if any intervention units are allocated; per-unit fees apply to all allocated intervention units, including partial lots.

For each policy:

```text
total_estimated_cost = residual_penalty + action_cost
saving_vs_no_action = no_action_exposure − total_estimated_cost
```

Savings may be negative. Sort policies by total cost ascending. Equal totals retain `accept_delay`, then `expedite_shipping`, then `alternative_supplier` priority. The first policy is recommended. No-delay scenarios do not incur unnecessary action fees and recommend accepting the baseline.

This compares **three fixed FIFO policies**, not every possible allocation or mix of actions. In particular, a partial lot can incur fees without reducing an order's penalty; a later improvement may skip such lots or optimize across orders, while preserving the agreed contract and explicit assumptions.

## Known-answer fixture scenarios

| Scenario | No-action exposure | Ranked totals and recommendation |
| --- | --- | --- |
| Alpha +0 days | £0.00 | All £0; `accept_delay` wins deterministic tie |
| Alpha +5 days | £500.00 | Expedite £160, alternative £260, accept £500; expedite recommended |
| Beta +5 days | £250.00 | Expedite £145, alternative £190, accept £250; expedite recommended |
| Alpha +30 days | £3,000.00 | Alternative £260 is cheapest; five saved days cannot remove the large disruption |

For Alpha +5, ten on-hand units cover `ORD-1001`. `ORD-1002` has twenty shortfall units, due 27 October and completing 1 November: `5 × £100 = £500`. Expedite reaches 27 October: `£100 + 20 × £3 = £160`, no residual penalty. Alternative sourcing also reaches 27 October: `£100 + 20 × £8 = £260`.

Gamma illustrates limited capacity: at +5, alternative capacity is eight units against a ten-unit shortfall. The order remains four days late (£220); the £136 action fee raises that policy's total to £356, so it is not recommended. This limitation is visible in policy details.

## Evidence and limits

Evidence includes stable fixture IDs and source references for the supplier, inventory, orders and recovery offer. These references identify local fixture records; they are not authenticated live-source links or an agent execution trace.

Dates use calendar days; weekends, holidays, transit, cancellation, split-delivery benefit, tax and common base procurement costs are excluded. The fixture assumes a single scheduled replenishment can cover demand. Unused regular/alternative stock has no modeled charge. Recovery costs are incremental hypothetical fees. Exposure is not actual revenue loss and no action is executed.

## Future integrations

- `integrations/zetaris.py`: `ZetarisRepository.status()` reports `not_configured`; `snapshot()` raises `IntegrationNotConfigured`. Developer 1 implements authenticated bounded read-only federation, provenance and failure tests. Never silently fall back to fixtures after a live-mode failure.
- `integrations/meterless.py`: `InferenceProvider` describes completion input/output including model and receipt IDs. `MeterlessClient.status()` reports pending Nightshift and Engine; `complete()` raises `IntegrationNotConfigured`. Developer 2 adds real model discovery/completions, a working Meterless Engine, Planner/Investigator/Evaluator flow, bounded retry and evidence validation.
- NVIDIA Nemotron remains optional future inference with actual usage receipts. It is not connected in this baseline.

Adding environment variables is not an integration. The baseline reads no credentials, downloads no model and reconfigures no existing installation. Future live mode and any new API fields require explicit team design/agreement before changing the frozen contract.
