# Meterless integration: Nightshift Runtime and the H-MEM Engine

Owner: Developer 2. Everything below was executed on the development machine on 27 October 2026 unless marked
otherwise. For the agent design, see [AGENT_ARCHITECTURE.md](AGENT_ARCHITECTURE.md).

## Summary for judges and sponsors

| Question | Answer |
| --- | --- |
| Runtime used | **Meterless Nightshift 1.2.1** (Windows), OpenAI-compatible API at `127.0.0.1:8088/v1`, reached from WSL through a local relay at `127.0.0.1:18088/v1` |
| Model | Routing id `meterless/local` (on-device only). Nightshift served it with `local-runtime/qwen2.5-coder-3b-instruct` (Qwen2.5-Coder 3B, GGUF, Vulkan on an RTX 3060 Laptop GPU). Every call returns a **signed** compute receipt, recorded in the report |
| Engine used | **Meterless H-MEM** (hierarchical memory): the official Apache-2.0 reference `@meterless/hmem-reference` 0.1.0 from `Meterless/Meterless@1742dec`, vendored unmodified and run in Node |
| How agents do work | A Planner turns the incident into tool tasks. An Investigator calls six explicit tools over the data repository and the deterministic simulator, then drafts a claim citing evidence ids. An Evaluator verifies every figure, order and evidence id and forces bounded retries |
| How context is retained | Each validated investigation is written to H-MEM with provenance (`plan_completion`, evidence refs), tags and confidence. Later incidents query H-MEM, and recalled memories shape the plan. Memory confidence is updated by outcome feedback, conflicts with newer findings are detected, and all of it is audited in H-MEM's append-only trust ledger |
| How responses are checked | Ten deterministic checks against exact `Decimal` results and recorded tool outputs. Nightshift's own cross-check status is also recorded per call. Unvalidated output never becomes a recommendation and is never written to memory |
| Beyond a chatbot | The model's output is a falsifiable claim: plans run real tools, every number is verified, wrong drafts are rejected with reasons and corrected, and outcomes accumulate as audited, provenance-tracked memory that later investigations use but cannot be overridden by |
| NVIDIA | **Not used.** No NVIDIA Nemotron or NVIDIA-hosted inference served any request. Nemotron GGUFs appear in Nightshift's catalogue, but none is installed, and the hosted NVIDIA provider was blocked on account verification. Every receipt shows `local-runtime/qwen2.5-coder-3b-instruct` |

## Nightshift Runtime

### Discovery (what was verified)

| Item | Finding |
| --- | --- |
| Base URL | Windows processes: `http://127.0.0.1:8088/v1`. WSL: `http://127.0.0.1:18088/v1` (the `meterless-bridge` relay, already present) |
| Auth | `Authorization: Bearer <token>`. The token is Nightshift's own `%LOCALAPPDATA%\ai.meterless.runtime\proxy-token`. `GET /v1/models` without it returns **401**. |
| Discovery | `GET /v1/models` returned 69 ids: routing ids (`meterless/auto`, `meterless/local`, `meterless/code`, …) and catalogue models (`local-runtime/*`) |
| Routing id chosen | `meterless/local`: on-device only, matching the privacy goal; it resolves to the installed Qwen 3B lane |
| Response | OpenAI `chat.completion`, plus `meterless` (`requested_model`, `routed_model`, `winning_route.{model,provider}`, `receipt_id`, `receipt_envelope`, `usage.latency_ms`) and `meterless_cross_check` (`status`, checks) |
| Latency | About 5–10 s per agent call. A full investigation takes 15–40 s (2–3 calls) |

Before this work could run, Nightshift was not running: its last log line was a clean `shutting down` on 25 Oct. Its
model lane was also refused admission ("needs 5451 MB of commit … 3680 MB free"), because the WSL VM held about 7 GB
of reclaimable page cache. Fixing that took two non-configuration steps: starting Nightshift with the existing launcher,
and dropping WSL's clean page cache (`echo 1 > /proc/sys/vm/drop_caches`). No Nightshift, WSL or Docker settings were
changed.

### Client (`backend/app/integrations/meterless.py`)

- `MeterlessConfig.from_env()` reads `METERLESS_BASE_URL`, `METERLESS_API_TOKEN` **or** `METERLESS_TOKEN_FILE`
  (preferred: it points at Nightshift's token file, so nothing secret is copied), `METERLESS_MODEL` (default
  `meterless/local`), `METERLESS_APP` (sent as `meterless-app`), timeouts and `METERLESS_MAX_RETRIES`. The token is
  excluded from `repr`, never logged and never put in error messages.
- `NightshiftClient.models()` and `.chat(messages, max_tokens, temperature)`.
- Retries with jittered backoff apply only to transient failures: connection errors, timeouts, 429, 502/503/504 and
  other 5xx (including Nightshift's 503 "The local runtime is not ready"). 401/403 raise `MeterlessAuthError`
  immediately. Other 4xx responses raise `MeterlessResponseError`. Exhausted retries raise `MeterlessUnavailable`. An
  empty or malformed completion raises `MeterlessResponseError`.
- `parse_completion` keeps text, routed model, provider, receipt id, whether the receipt is signed, tokens, latency
  and the cross-check status.
- `MeterlessClient()` with no configuration still reports `not_configured` and refuses to complete. That keeps the
  original placeholder contract and tests.

### Live verification

```text
$ python -m scripts.agent_smoke
Nightshift http://127.0.0.1:18088/v1: 69 routing ids; requested meterless/local (listed)
H-MEM engine: {'engine': 'H-MEM', 'package': '@meterless/hmem-reference', 'version': '0.1.0', 'persistent': True, 'records': 0}
== SUP-ALPHA +5 days -> validated
  attempt 1: rejected ['exposure_matches', 'explanation_grounded'] (claimed expedite_shipping, exposure 0.00, cost 160.00)
  attempt 2: validated  (claimed expedite_shipping, exposure 500.00, cost 160.00)
  Nightshift: requested meterless/local -> ['local-runtime/qwen2.5-coder-3b-instruct'] via ['local-runtime']; 3 calls, 3 signed receipts
  H-MEM stored mem-1; ledger {'create': 1}
== SUP-ALPHA +6 days -> validated
  H-MEM recall: mem-1 (0.4889)
  attempt 1: validated  (claimed expedite_shipping, exposure 600.00, cost 260.00)
  H-MEM stored mem-2; feedback [mem-1 helpful]; conflicts [(mem-1, mem-2, 'high-similarity conflicting numeric values')]
  ledger {'create': 2, 'read': 1, 'feedback': 1, 'conflict_detected': 1}
RESULT: PASS
```

`AGENT_LIVE_TESTS=1 python -m pytest tests/test_agent_live.py -v -s` passed 2/2: a real `PONG` completion with a
signed receipt, and two real investigations with H-MEM recall.

Live reliability sweep: six investigations, one shared H-MEM store, real model.

| Scenario | Result | Drafts | Evaluator rejections on the way |
| --- | --- | --- | --- |
| Beta +5 | validated, expedite £145 (exposure £250) | 2 | exposure, explanation |
| Gamma +5 | validated, expedite (exposure £220) | 1 | none |
| Alpha +0 | validated, accept_delay (exposure £0) | 2 | affected orders, explanation |
| Alpha +30 | **unresolved**: no recommendation returned, nothing stored | 3 | wrong strategy in all three drafts (deterministic answer: alternative_supplier) |
| Alpha +5 (memory recalled) | validated, expedite £160 | 1 | none |
| Beta +5 (memory recalled) | validated, expedite £145 | 2 | exposure, explanation |

So with the 3B model, 5 of 6 validated. The sixth failed safely instead of returning a wrong recommendation.

## Meterless Engine: H-MEM

### Why H-MEM, and why the reference implementation

The hackathon guide (`Meterless/Meterless/docs/community/hackathon-guide.md`) points builders at the open engines in
`engines/`. Nightshift contains its own H-MEM tier (`engine/js/engine/hmem.js`), but it runs only inside Nightshift's
routing and has no HTTP API an application can call. The repository's `engines/hmem/reference` is the official
runnable implementation of the H-MEM spec: deterministic, zero dependencies, Apache-2.0. It is vendored unmodified in
`backend/engines/hmem/src` (commit and SHA-256 hashes are in `backend/engines/hmem/VENDORED.md`) and reviewed: it makes
no network calls, runs no subprocesses, and writes only `state.json` / `ledger.jsonl` in the given directory.

### How it runs

`backend/app/integrations/hmem.py` starts
`node --experimental-transform-types --no-warnings backend/engines/hmem_bridge.mjs`. That process holds one `HMEM`
instance and speaks JSON lines over stdin/stdout. Requires Node 22.7+; the development machine uses Node 24.22.1 in WSL.
State persists in `SENTRY_HMEM_DIR` (default `~/.local/state/sentry-ai/hmem`, outside the repository).

| Python call | Engine API used | Where in the workflow |
| --- | --- | --- |
| `HMemEngine.query(key, top_n=3, threshold=0.45)` | `HMEM.query` → `MemoryRetrievalService.query` (hybrid ranking, `read` ledger entries, reinjection block) | Before planning: recall prior investigations |
| `HMemEngine.add(...)` | `HMEM.add` → `MemoryStoreService.add` (source required, enrichment, relationships, `create` ledger entry) | After a **validated** investigation only |
| `HMemEngine.feedback(id, kind)` | `HMEM.feedback` (exact confidence deltas, `feedback` ledger entry) | Recalled memory: `helpful` if its strategy still holds, `not_helpful` if not |
| `HMemEngine.scan_conflicts()` | `ConflictDetectionService.scan` (`conflict_detected` ledger entries) | After write-back: flags the old memory whose figures differ from the new finding |
| `HMemEngine.stats()` / `history(id)` | `TrustLedgerService.stats` / `history` | Ledger totals in every report |

Stored record example (from a live run):

```text
content: Supplier disruption SUP-ALPHA Alpha Components SKU-SENSOR delayed 5 days. Validated recommendation
         expedite_shipping. Affected orders ORD-1002. Exposure GBP 500.00; expedite_shipping total GBP 160.00 as of
         2026-10-25 (re-verify: figures go stale). Evidence supplier:SUP-ALPHA, inventory:SKU-SENSOR, order:ORD-1001,
         order:ORD-1002, recovery:SUP-ALPHA.
source: sentry-ai://investigations/inv-…   provenance: plan_completion, refs = evidence ids
tags: supplier:SUP-ALPHA, sku:SKU-SENSOR, strategy:expedite_shipping, delay:5   layer: long_term   confidence: 0.9
```

### Observed behaviour and safeguards

- **Recall is selective.** With the engine's own scoring, a same-supplier incident scores about 0.49–0.56 and other
  suppliers about 0.38–0.40. The default threshold of 0.35 would recall everything, so Sentry passes `threshold=0.45`.
- **Memory shapes the plan.** A recalled `strategy:` tag adds a `memory`-origin re-check task, and the planner prompt
  includes the memory marked "context only".
- **Memory cannot override current data.** In a live Alpha +6 run, the model's first draft claimed the remembered £160
  instead of the current £260. The evaluator rejected it (`cost_matches`), and the retry used £260. In
  `test_stale_memory_figures_cannot_override_current_data`, a model that keeps repeating stale figures ends
  `unresolved` and nothing is stored.
- **Outcome feedback is real.** Alpha +30 makes `alternative_supplier` cheapest, so the Alpha +5 memory
  (`expedite_shipping`) gets `not_helpful`, which lowers its confidence through the engine. This is verified with the
  real engine and a scripted model (`test_memory_whose_strategy_no_longer_holds_is_marked_not_helpful`). In the live
  sweep the 3B model did not validate Alpha +30, so no feedback was written there.
- **Conflicts are detected.** The engine flags old and new findings for the same situation with different figures
  (`high-similarity conflicting numeric values`); they appear in `memory.conflicts`.

### Engine tests (real engine, no mocks)

`tests/test_meterless.py`: provenance and ledger, the selective recall threshold, rejection of records without a
source, conflict detection, and persistence across engine processes. `tests/test_agent.py`: recall shapes the plan,
stale figures are rejected, and feedback reflects outcomes. These tests skip only when Node 22.7+ is unavailable. The
backend CI job currently runs no Node setup step, so in CI they skip unless one is added.

## Configuration

Repository-root `.env` (gitignored), as used on the development machine:

```bash
METERLESS_BASE_URL=http://127.0.0.1:18088/v1      # Windows processes: http://127.0.0.1:8088/v1
METERLESS_TOKEN_FILE=/mnt/c/Users/<you>/AppData/Local/ai.meterless.runtime/proxy-token
METERLESS_MODEL=meterless/local
METERLESS_APP=sentry-ai
# optional: SENTRY_HMEM_DIR=/path/to/state  SENTRY_NODE=/path/to/node
```

Each teammate needs Nightshift running with a model lane, Node 22.7+ on `PATH` for the backend, and these settings.
Then run `python -m scripts.agent_smoke`.

## Limitations

- The 3B local model often needs a second draft, so the evaluator, not the model, is what guarantees correctness.
  Pinning a larger lane in Nightshift needs no code change.
- H-MEM retrieval in the reference uses its deterministic hash embedder (lexical similarity), as upstream ships it.
- One investigation runs at a time per backend process, because the persistent H-MEM store is a single JSON file.
- `/api/health` still reports `meterless: "not_configured"` until the team agrees the contract change
  ([AGENT_ARCHITECTURE.md](AGENT_ARCHITECTURE.md#decisions-for-the-team)).
