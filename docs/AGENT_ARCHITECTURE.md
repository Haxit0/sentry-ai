# Agent architecture: Planner → Investigator → Evaluator

Owner: Developer 2 (`feature/agent-recovery`, issue #2). This page covers the investigation agent, its evidence trace,
and the additive `POST /api/investigations` endpoint. For the Meterless runtime and the H-MEM Engine, see
[METERLESS_INTEGRATION.md](METERLESS_INTEGRATION.md).

## Principle

The model investigates and explains; it never calculates. Every financial figure comes from the existing deterministic
`Decimal` simulator. Every model claim is checked against tool outputs before it can become a recommendation.
If validation keeps failing, the report says `unresolved` and lists the problems; it never invents success.

```text
POST /api/investigations {"supplier_id": "SUP-ALPHA", "delay_days": 5}
        │
        ▼
 H-MEM recall ──────────────── Meterless H-MEM engine: query(similar prior incidents)
        │   (context only; may be stale)
        ▼
 Planner agent ─────────────── Nightshift completion → JSON tasks over allowlisted tools
        │   + coverage policy (required tools) + memory-derived re-check tasks
        ▼
 Investigator agent
   1. executes each task's tool (arguments bound from the incident, never from model text)
   2. Nightshift completion → structured claim citing evidence_ids
   3. re-investigation: resolves every cited evidence id via get_evidence, re-runs missing tools
        │
        ▼
 Evaluator agent (deterministic) ── 10 checks against tool outputs + Decimal simulation
        │ fail → explicit feedback → Investigator retries (max 3 drafts)
        │ pass ↓
 Report: validated recommendation, explanation, evidence ids, trace
        │
        ▼
 H-MEM write-back ─────────── add(validated finding, provenance) · feedback(recalled memories)
                               · scan_conflicts() · ledger stats
```

## Code map

| File | Role |
| --- | --- |
| `backend/app/integrations/meterless.py` | Nightshift client: discovery, completions, retries, errors, receipts |
| `backend/app/integrations/hmem.py`, `backend/engines/` | Meterless H-MEM engine (vendored reference) and its Node bridge |
| `backend/app/agents/tools.py` | Six explicit tools over one pinned repository snapshot |
| `backend/app/agents/planner.py` | Planner agent and coverage policy |
| `backend/app/agents/investigator.py` | Tool execution, claim drafting, re-investigation |
| `backend/app/agents/evaluator.py` | Deterministic claim verification |
| `backend/app/agents/llm.py` | Receipt accounting and tolerant JSON extraction |
| `backend/app/agents/schemas.py` | Report models (separate from the frozen `app/schemas.py`) |
| `backend/app/services/agent_investigation.py` | Orchestration, bounded retries, memory write-back |
| `backend/app/agents/router.py` | Additive FastAPI endpoint |
| `backend/scripts/agent_smoke.py` | Live end-to-end smoke test |

## Tools

| Tool | Arguments (bound from the incident) | Returns | Evidence ids |
| --- | --- | --- | --- |
| `get_supplier` | `supplier_id` | Supplier record with expedite and alternative offers | `supplier:<id>` |
| `get_inventory` | `sku` (from the supplier record) | On-hand units | `inventory:<sku>` |
| `get_orders` | `supplier_id` | Dependent orders, promised-date order | `order:<id>`… |
| `run_disruption_simulation` | `supplier_id`, `delay_days` | Disrupted date, late orders, exposure | `order:<late id>`… |
| `get_recovery_options` | `supplier_id`, `delay_days` | The three ranked policies with exact costs | `recovery:<id>` |
| `get_evidence` | `evidence_id` | One evidence record (source and description) | that id |

All tools read one snapshot taken at the start (`PinnedRepository`), so the trace is internally consistent. They work
with any `DataRepository`: the fixture today, or Developer 1's `ZetarisRepository`. This was verified by merging PR #5
into a scratch worktree and running mocked and live Zetaris investigations, with evidence resolving to
`zetaris://SENTRY_ERP_PG…` and `zetaris://SENTRY_SUPPLIER_PORTAL…` sources. The Zetaris protocol is not duplicated.

## Planner

The model receives the incident, the tool list and any recalled memories (marked "context only, never reuse its
figures"). It replies with `{"tasks": [{"question", "tool"}]}`. Tasks naming unknown tools are rejected and noted in
`plan_notes`. A coverage policy appends any of the five required tools that the model skipped (origin
`coverage_policy`). A recalled memory with a `strategy:` tag adds a re-check task (origin `memory`). Each step keeps its
origin, so the trace shows what the model planned and what the policy added.

## Evaluator checks

| Check | Fails when |
| --- | --- |
| `required_tools_called` | Any required tool has no successful result |
| `strategy_exists` | The claimed strategy is not one of the three options |
| `strategy_matches_calculation` | The claimed strategy is not the deterministic cheapest |
| `order_ids_valid` | A claimed order id does not exist |
| `affected_orders_match` | The claimed late orders differ from the simulation |
| `exposure_matches` | The claimed exposure is not exactly the `Decimal` exposure |
| `cost_matches` | The claimed cost is not that option's exact total |
| `evidence_exists` | No evidence is cited, or a cited id fails to resolve through `get_evidence` |
| `evidence_supports_recommendation` | The recovery offer or any late order's evidence is not cited |
| `explanation_grounded` | The explanation is empty, states a GBP figure not present in the tool outputs, uses a percentage, or names an order that is not late |

Each failure produces a concrete correction for the next draft, for example "penalty_exposure_gbp must be copied from
the tool output: 500.00", or a quote of the offending sentence. Unparseable replies count as attempts. After three
drafts the report is `unresolved`. In that case `recommended_strategy`, `explanation` and `recommended_total_cost_gbp`
are `null`, `validation.unresolved` lists what failed, and nothing is written to memory. The deterministic
`calculated_recommendation` is still reported, clearly labelled as a calculated fact.

Observed on the real model (Qwen2.5-Coder 3B via Nightshift): first drafts are sometimes wrong. Examples include an
exposure of `0.00`, the previous scenario's £160 cost recalled from memory, an invented "50% saving", and an unaffected
order named as impacted. The evaluator caught each one, and the retry corrected it. That retry loop is the point of the
design.

## Proposed contract addition (needs team agreement)

The v1 contract stays frozen: `/api/health`, `/api/suppliers`, `/api/orders` and `/api/simulations` are unchanged, and
their `"fixture"` / `"not_configured"` literals still hold. This branch adds one endpoint:

### `POST /api/investigations`

Request: identical rules to `POST /api/simulations`, i.e. `{"supplier_id": "SUP-ALPHA", "delay_days": 5}`, a strict
integer from 0 to 30, with no extra keys.

| Status | Meaning |
| --- | --- |
| 200 | Report returned. Check `status`: `validated` or `unresolved` |
| 404 | Unknown supplier, `{"detail": "Unknown supplier: …"}` |
| 422 | Invalid request (same rules as simulations) |
| 503 | Nightshift or H-MEM not configured, unreachable or failing. `detail` names the error type. No fallback answer |

Expect a typical latency of 15–40 s on the local 3B model, covering two or three Nightshift calls. Show progress in
the UI.

Key response fields (full model: `backend/app/agents/schemas.py`; OpenAPI at `/docs`):

| Field | Meaning |
| --- | --- |
| `status` | `validated` or `unresolved` |
| `recommended_strategy`, `recommended_total_cost_gbp`, `explanation`, `supporting_evidence_ids` | Agent output. `null` / empty unless validated |
| `calculated_recommendation`, `estimated_penalty_exposure_gbp`, `recovery_options`, `affected_orders` | Deterministic facts (same types as simulations) |
| `hypotheses` | Model-stated assumptions: not facts, show as such |
| `plan[]` | `task_id`, `question`, `tool`, `origin` (`planner` / `coverage_policy` / `memory`) |
| `tool_calls[]` | `call_id`, `task_id` (or `RETRY`), `tool`, `arguments`, `status`, `summary`, `evidence_ids`, `result` |
| `validation` | `passed`, `checks[]`, `attempts[]` (each with the claim and failed checks), `unresolved[]` |
| `model` | Requested routing id, models used, providers, receipt ids, signed receipt count, tokens |
| `memory` | H-MEM implementation, query, `recalled[]`, `stored_memory_id`, `feedback[]`, `conflicts[]`, `ledger` |
| `data_source`, `disclaimer` | `fixture` today; disclosure text |

Money is encoded exactly as in v1: two-decimal strings.

Real response from `POST /api/investigations` on the development machine (Alpha +5, 27 Oct 2026, trimmed where marked):

```json
{
  "investigation_id": "inv-5caaf298f331",
  "status": "validated",
  "incident": {"supplier_id": "SUP-ALPHA", "supplier_name": "Alpha Components", "sku": "SKU-SENSOR", "delay_days": 5,
               "summary": "Supplier SUP-ALPHA (Alpha Components, SKU SKU-SENSOR) reports its scheduled restock on 2026-10-27 will arrive 5 days late. Evaluation date 2026-10-25."},
  "as_of_date": "2026-10-25",
  "disrupted_restock_date": "2026-11-01",
  "plan": [
    {"task_id": "T1", "question": "What is the scheduled restock date for SKU SKU-SENSOR from Supplier SUP-ALPHA?", "tool": "get_supplier", "origin": "planner"},
    {"task_id": "T4", "question": "What is the penalty exposure if the restock is delayed by 5 days?", "tool": "run_disruption_simulation", "origin": "planner"},
    "… 6 steps …"
  ],
  "plan_notes": [],
  "tool_calls": [
    {"call_id": "call-2", "task_id": "T2", "tool": "get_inventory", "arguments": {"sku": "SKU-SENSOR"}, "status": "ok",
     "summary": "10 on-hand units of SKU-SENSOR as of 2026-10-25", "evidence_ids": ["inventory:SKU-SENSOR"],
     "result": {"sku": "SKU-SENSOR", "on_hand_units": 10}},
    {"call_id": "call-4", "task_id": "T4", "tool": "run_disruption_simulation", "arguments": {"supplier_id": "SUP-ALPHA", "delay_days": 5},
     "status": "ok", "summary": "Restock moves to 2026-11-01; 1 late orders (ORD-1002); exposure GBP 500.00",
     "evidence_ids": ["order:ORD-1002"], "result": "…"},
    "… 10 calls, including RETRY get_evidence lookups …"
  ],
  "affected_orders": ["… ORD-1002, 5 days late, estimated_penalty_gbp \"500.00\" …"],
  "estimated_penalty_exposure_gbp": "500.00",
  "recovery_options": [
    {"strategy": "expedite_shipping", "residual_penalty_gbp": "0.00", "action_cost_gbp": "160.00", "total_estimated_cost_gbp": "160.00", "saving_vs_no_action_gbp": "340.00", "details": "…"},
    {"strategy": "alternative_supplier", "residual_penalty_gbp": "0.00", "action_cost_gbp": "260.00", "total_estimated_cost_gbp": "260.00", "saving_vs_no_action_gbp": "240.00", "details": "…"},
    {"strategy": "accept_delay", "residual_penalty_gbp": "500.00", "action_cost_gbp": "0.00", "total_estimated_cost_gbp": "500.00", "saving_vs_no_action_gbp": "0.00", "details": "…"}
  ],
  "calculated_recommendation": "expedite_shipping",
  "recommended_strategy": "expedite_shipping",
  "recommended_total_cost_gbp": "160.00",
  "explanation": "Supplier SUP-ALPHA's scheduled restock on 2026-10-27 will arrive 5 days late, impacting 1 order (ORD-1002). The cheapest recovery option is to expedite shipping, which costs GBP 160.00 without additional delay. This option minimizes the penalty exposure of GBP 500.00.",
  "supporting_evidence_ids": ["supplier:SUP-ALPHA", "inventory:SKU-SENSOR", "order:ORD-1001", "order:ORD-1002", "recovery:SUP-ALPHA"],
  "hypotheses": ["All reported data is accurate and up-to-date.", "…"],
  "validation": {
    "passed": true, "attempts_used": 2, "max_attempts": 3,
    "checks": [{"check": "exposure_matches", "passed": true, "detail": "claimed '500.00'; calculated 500.00"}, "… 10 checks …"],
    "attempts": [
      {"attempt": 1, "outcome": "rejected", "failed_checks": ["exposure_matches", "explanation_grounded"],
       "retry_reason": "penalty_exposure_gbp must be copied from the tool output: 500.00; rewrite the explanation without these sentences, …: \"… resulting in a 50% cost savings …\". Use only GBP figures copied from the tool outputs and no percentages",
       "claim": {"penalty_exposure_gbp": "0.00", "…": "…"}},
      {"attempt": 2, "outcome": "validated", "failed_checks": [], "retry_reason": null, "claim": {"…": "…"}}
    ],
    "unresolved": []
  },
  "model": {"runtime": "meterless-nightshift", "requested_model": "meterless/local",
            "models_used": ["local-runtime/qwen2.5-coder-3b-instruct"], "providers": ["local-runtime"],
            "receipt_ids": ["rcpt_req_86ghdpyv", "rcpt_req_t41abgz6", "rcpt_req_yd585ght"], "signed_receipts": 3, "calls": 3,
            "prompt_tokens": 5645, "completion_tokens": 1060},
  "memory": {"engine": "H-MEM", "implementation": "@meterless/hmem-reference 0.1.0 (Meterless/Meterless@1742dec)", "persistent": true,
             "query": "Supplier disruption SUP-ALPHA Alpha Components SKU-SENSOR delayed 5 days", "recalled": [],
             "stored_memory_id": "mem-1", "feedback": [], "conflicts": [], "ledger": {"create": 1}},
  "data_source": "fixture",
  "disclaimer": "Agent investigation over fixture data. …"
}
```

In this captured response the second draft still said "impacting 2 orders (ORD-1001, ORD-1002)". That mistake led to
the `explanation_grounded` rule that named orders must be late. Later live runs produce "impacting 1 order (ORD-1002)".

## What Developer 3 needs

1. `POST /api/investigations` with `{supplier_id, delay_days}`. The Vite `/api` proxy and CORS already cover it.
2. Show a progress state (15–40 s). Treat a 503 as "agent runtime unavailable" and show `detail`. Never substitute simulation output as an agent answer.
3. Show the headline only when `status == "validated"`: `recommended_strategy`, `recommended_total_cost_gbp`, `explanation`. When `unresolved`, show `validation.unresolved` and the deterministic `calculated_recommendation` labelled as a calculation, not an agent recommendation.
4. Evidence trace: render `plan` (with an origin badge), `tool_calls` (summary, status, evidence chips), `validation.checks` and `validation.attempts` (rejected drafts with their failed checks). Use `supporting_evidence_ids` to highlight `tool_calls[].evidence_ids` and `get_evidence` results.
5. Memory panel: `memory.recalled` (relevance, "context only"), `memory.feedback`, `memory.conflicts`, `memory.stored_memory_id`.
6. Model panel: `model.models_used`, `model.receipt_ids`, `model.signed_receipts`.
7. TypeScript types can mirror `backend/app/agents/schemas.py`. The OpenAPI schema at `/openapi.json` includes them.

## Decisions for the team

- Approve `POST /api/investigations` as an additive v1.1 endpoint, then copy the table above into `CONTRACT.md`.
- `/api/health` still reports `meterless: "not_configured"` because those literals are frozen. Proposal: allow
  `"connected"` / `"unavailable"` once agreed, together with the Zetaris statuses proposed in PR #5.
- Once PR #5's `SENTRY_DATA_MODE` is agreed, `get_investigation_repository` can return the Zetaris repository. The agent
  needs no other change.
