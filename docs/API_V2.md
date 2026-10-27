# Versioned submission API

Base: `/api/v2`. The compatibility API and `/legacy` remain unchanged.

| Endpoint | Behavior |
| --- | --- |
| GET `/status` | Data mode, successful source acquisition, Nightshift discovery and H-MEM availability. Discovery does not prove inference readiness. |
| GET `/cases` | Named synthetic scenarios and default inputs. |
| GET `/workspace` | Supplier/order records and snapshot provenance. |
| POST `/simulations` | Exact calculated options, constraint eligibility, 31 delay scenarios and uncertainty. |
| POST `/investigation-runs` | HTTP 202 with durable run ID. One running/two queued maximum; 429 when full. |
| GET `/investigation-runs` | Thirty most recent local runs. |
| GET `/investigation-runs/{id}` | Recorded inputs, state, events, report, error and reviews. |
| POST `/investigation-runs/{id}/cancel` | Cooperative cancellation; active model calls may finish before cancellation is observed. |
| POST `/investigation-runs/{id}/review` | `approve`, `request_revision`, `defer`; optional note. Approval requires validation. No external action. |
| GET `/investigation-runs/{id}/export` | Sanitized JSON packet; `?format=markdown` provides readable Markdown. |

Decision inputs: strict integer `delay_days` (0–30), `supplier_id`, `case_id`, optional
`max_action_cost_gbp` (two-decimal money), optional integer `max_late_days` (0–60), and
`compare_strategy` from the three policies. Unknown fields are rejected. The budget applies to
action fees; the lateness limit applies to the worst remaining whole-order delay. Eligible policies
retain deterministic ranking/ties. No eligible policy means no recommendation.

States: queued, running, validated, unresolved, failed, cancelled. Restarted unfinished work becomes
failed rather than replaying silently. Data errors return 503 on synchronous routes or a named failed
asynchronous run. No live-to-fixture fallback exists. Content hashes exclude retrieval/query IDs.

Money remains exact GBP strings. Data stays synthetic. The API is loopback-only, single-workspace,
single-worker software. It is not a public multi-tenant service. Receipt signature presence is counted;
independent cryptographic verification is not implemented.

`GET /api/v2/investigation-runs/{id}/comparison?against={other_id}` compares stored inputs, validated costs and snapshot hashes. Monetary differences use Decimal; they are not realized savings.
