# Frozen API contract v1

This is the shared boundary for three parallel feature branches. **Do not change field names, types, serialization, endpoint behavior or status meanings without team agreement.** After agreement, update this document, `backend/app/schemas.py`, frontend types and tests together. The running schema is available at `/openapi.json` and `/docs`.

Base path: `/api`. Backend: `http://127.0.0.1:8000`. Local dashboard: `http://localhost:5173` or `http://127.0.0.1:5173`, with a Vite `/api` proxy. The API allows these two development origins.

## Encoding and rules

- JSON objects; dates are ISO `YYYY-MM-DD` strings.
- GBP money is a JSON **string with exactly two decimal places**, for example `"160.00"`. Backend arithmetic is exact `Decimal`. The UI converts only for display.
- Money is bounded to 14 digits with at most two decimal places in Pydantic models. Costs/penalties are nonnegative; `saving_vs_no_action_gbp` may be negative.
- Quantities, capacities, durations and late days are integers. Identifiers and descriptions are strings.
- All listed response fields are required. No pagination or wrapper object on list endpoints.
- Evaluation date is fixed to `2026-10-25`; fixture records are synthetic. No actual recovery action occurs.
- The models forbid extra fields. The simulation request requires a strict integer: booleans, fractional values and numeric strings are rejected.

## `GET /api/health` → 200

```json
{
  "status": "ok",
  "execution_mode": "fixture",
  "as_of_date": "2026-10-25",
  "agent_status": "not_configured",
  "integrations": {
    "zetaris": "not_configured",
    "meterless": "not_configured"
  }
}
```

Health validates fixture loading. `ok` means this fixture application can operate; it does not claim external integration health. `meterless` covers the still-pending Nightshift/Engine work. Actual agent inference and NVIDIA are not connected.

## `GET /api/suppliers` → 200

Returns `Supplier[]` containing three primary suppliers. Alternative offers are nested, not additional primary entries.

| Supplier field | Type | Meaning |
| --- | --- | --- |
| `supplier_id` | string | Stable primary ID, e.g. `SUP-ALPHA` |
| `name` | string | Display name |
| `sku` | string | Unique SKU supplied |
| `restock_date` | date | Original scheduled restock |
| `replenishment_quantity` | positive integer | Scheduled units; fixture validation ensures total supply covers demand |
| `expedite` | ExpediteOption | Hypothetical expedited offer |
| `alternative` | AlternativeSupplier | Hypothetical alternative offer |

`ExpediteOption`: `days_saved` (nonnegative integer), `capacity_units` (nonnegative integer), `fixed_fee_gbp` (money), `per_unit_fee_gbp` (money).

`AlternativeSupplier`: `supplier_name` (string), `lead_time_days` (nonnegative integer from evaluation date), `capacity_units` (nonnegative integer), `fixed_fee_gbp` (money), `unit_premium_gbp` (money).

Example supplier:

```json
{
  "supplier_id": "SUP-ALPHA",
  "name": "Alpha Components",
  "sku": "SKU-SENSOR",
  "restock_date": "2026-10-27",
  "replenishment_quantity": 40,
  "expedite": {
    "days_saved": 5,
    "capacity_units": 40,
    "fixed_fee_gbp": "100.00",
    "per_unit_fee_gbp": "3.00"
  },
  "alternative": {
    "supplier_name": "Northstar Components",
    "lead_time_days": 2,
    "capacity_units": 20,
    "fixed_fee_gbp": "100.00",
    "unit_premium_gbp": "8.00"
  }
}
```

## `GET /api/orders` → 200

Returns `Order[]`, all six synthetic development orders.

| Order field | Type | Meaning |
| --- | --- | --- |
| `order_id` | string | Stable order ID |
| `customer_name` | string | Synthetic customer |
| `supplier_id` | string | Primary supplier ID |
| `sku` | string | One SKU per order |
| `quantity` | positive integer | Ordered units |
| `promised_date` | date | Promised completion date |
| `penalty_per_day_gbp` | money | Flat daily fee for a whole late order, not per unit |

## `POST /api/simulations` → 200

Request:

```json
{"supplier_id": "SUP-ALPHA", "delay_days": 5}
```

`supplier_id` must contain 1–80 characters and identify an existing supplier. `delay_days` is a strict integer from **0 through 30 inclusive**. No extra fields are accepted. Simulation is stateless and read-only; it consumes no global inventory.

| Response field | Type | Meaning |
| --- | --- | --- |
| `supplier_id` | string | Requested supplier |
| `delay_days` | integer | Requested injected delay |
| `as_of_date` | date | Fixed evaluation date |
| `disrupted_restock_date` | date | Original restock plus injected delay |
| `affected_orders` | AffectedOrder[] | Only orders late under no action, after FIFO inventory allocation |
| `estimated_penalty_exposure_gbp` | money | Sum of no-action late-order penalties |
| `recovery_options` | RecoveryOption[] | Exactly three policies, sorted cheapest first |
| `recommended_strategy` | Strategy | First ranked policy |
| `evidence` | Evidence[] | Source references and deterministic calculation explanations |
| `execution_mode` | literal `"fixture"` | Synthetic execution only |
| `agent_status` | literal `"not_configured"` | No actual agent workflow |
| `disclaimer` | string | Synthetic costs/integrations/no-action disclosure; wording is not a stable ID |

`AffectedOrder` includes every `Order` field plus:

| Field | Type | Meaning |
| --- | --- | --- |
| `inventory_allocated` | nonnegative integer | Warehouse units allocated by promised date, then order ID |
| `shortfall_units` | nonnegative integer | Quantity minus warehouse allocation |
| `expected_delivery_date` | date | No-action whole-order completion |
| `delay_days` | nonnegative integer | Order lateness relative to promise; distinct from injected supplier delay |
| `estimated_penalty_gbp` | money | Order late days × whole-order daily penalty |

`Strategy` is one of `"accept_delay"`, `"expedite_shipping"`, `"alternative_supplier"`.

| RecoveryOption field | Type | Meaning |
| --- | --- | --- |
| `strategy` | Strategy | Evaluated policy |
| `residual_penalty_gbp` | money | Remaining late-order penalty after policy |
| `action_cost_gbp` | money | Incremental fixed and per-unit fees actually incurred |
| `total_estimated_cost_gbp` | money | Residual penalty + action cost |
| `saving_vs_no_action_gbp` | money, signed | Exposure minus this policy's total |
| `details` | string | Arrival, capacity, used units, fees and limitations; display text, not a machine-parseable trace |

`Evidence` fields: `evidence_id` (string), `source` (string), `description` (string). Sources identify fixture records such as `backend/app/data/demo_data.json#orders/ORD-1002`; they are provenance labels rather than authenticated live URLs. Order evidence includes on-time allocations as well as late orders.

Policies retain stable tie order: accept, expedite, alternative. The recommendation is cheapest among these three fixed FIFO policies, not a claim of global optimization. Incomplete partial recovery still waits for remaining units; fees can make a policy worse than no action. See `ARCHITECTURE.md` for full assumptions.

### Golden scenario

For Alpha +5, `disrupted_restock_date` is `2026-11-01`; the only affected order is:

```json
{
  "order_id": "ORD-1002",
  "customer_name": "Beacon Manufacturing",
  "supplier_id": "SUP-ALPHA",
  "sku": "SKU-SENSOR",
  "quantity": 20,
  "promised_date": "2026-10-27",
  "penalty_per_day_gbp": "100.00",
  "inventory_allocated": 0,
  "shortfall_units": 20,
  "expected_delivery_date": "2026-11-01",
  "delay_days": 5,
  "estimated_penalty_gbp": "500.00"
}
```

| Sorted strategy | Residual penalty | Action cost | Total | Saving |
| --- | --- | --- | --- | --- |
| `expedite_shipping` | `"0.00"` | `"160.00"` | `"160.00"` | `"340.00"` |
| `alternative_supplier` | `"0.00"` | `"260.00"` | `"260.00"` | `"240.00"` |
| `accept_delay` | `"500.00"` | `"0.00"` | `"500.00"` | `"0.00"` |

Exposure is `"500.00"` and recommendation is `"expedite_shipping"`. Zero-delay fixtures return empty affected orders, `"0.00"` exposure and `"accept_delay"` through tie priority.

## Errors

- **404** unknown supplier: `{"detail":"Unknown supplier: SUP-UNKNOWN"}`.
- **422** invalid JSON/request: FastAPI validation `{"detail":[...]}` with locations, messages and validation types. Negative/>30 delay, missing fields, numeric strings, floats, booleans, empty ID and extra request keys are rejected. Do not depend on exact human-readable validation wording.
- **500** unexpected application/fixture error: never reinterpret as a successful simulation or silently supply frontend results. The dashboard presents a request error.

The fixture application exposes no live-mode request switch. Adding live integration or agent responses requires team agreement rather than changing these literals unilaterally.
