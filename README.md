# Sentry AI

**When a supplier slips, know why the recovery choice makes sense, and what would change it.**

Open Agent Hackathon 2026 · Track 2: The Agent That Can Explain Why.

Sentry helps supply-chain operations managers investigate delayed suppliers, compare recovery choices and produce reviewable decision packets. Zetaris federates PostgreSQL orders and CSV supplier, inventory and carrier records. Nightshift-powered agents investigate and challenge evidence. Exact financial checks block unsupported claims. Meterless H-MEM retains validated findings.

The business records are **synthetic**. Real connectors and real model calls do not turn them into customer data. Recommendations never execute purchases, shipments or customer changes.

## Demonstration

Alpha Components is five days late. Stock covers the first order, leaving ORD-1002 exposed to **GBP 500.00** in penalties. Expedited recovery totals **GBP 160.00**, versus **GBP 260.00** for alternative sourcing, a hypothetical **GBP 340.00** saving against no action.

At seven days, alternative sourcing becomes cheaper. A GBP 50 action budget and zero remaining lateness leave no feasible recovery. Conflicting arrival reports cause Sentry to withhold a firm AI recommendation and ask for confirmation.

## Agent collaboration

The Planner chooses evidence questions. The Investigator runs server-bound tools and drafts an evidence-cited explanation. A Nightshift Critic challenges unsupported claims. The deterministic Evaluator retains final veto over money, order IDs and citations. Missing evidence returns to the Planner for revised tasks. Rejected drafts, actual feedback and tool results remain in the trace.

H-MEM findings are historical context. Every current cost is recalculated. Only validated findings enter memory. Each snapshot records acquisition timestamps, query IDs, row counts and a SHA-256 content hash. The acquisition window is not an atomic transaction across sources.

One worker processes investigations, with two queued jobs maximum. Each run has three draft attempts, eight model calls, 32 tool calls and a 120-second processing budget. Cancellation is cooperative. Human review records approval, revision or deferral without executing an action.

## Sponsor and development-tool disclosure

| Technology | Actual role |
| --- | --- |
| Zetaris | Read-only federation, including a PostgreSQL/CSV cross-source join and an additional carrier/supplier update source. |
| Meterless Nightshift | Primary and only AI-provider path for Planner, Investigator and Critic calls, with returned model and receipt metadata. |
| Meterless H-MEM | Unmodified Apache-2.0 reference engine pinned at `1742dec56a66e58eef9dda2d2b865823758ca8cd`, used for persistent recall, feedback, conflict detection and its trust ledger. |
| NVIDIA | Local Qwen inference accelerated by CUDA on an RTX 4080 Laptop GPU. No Nemotron or hosted NVIDIA API claim. |
| Coding tools | This integration used OpenAI Codex and VS Code. Cursor usage by teammates is unconfirmed and is not claimed. |

The deterministic Evaluator is application code, not another model pretending to verify arithmetic. Source text and memories are untrusted data and cannot authorize commands or unrestricted SQL. See [component disclosure](docs/PROJECT_DESCRIPTION.md).

## Install and run

Requires Python 3.11+, Node 24, npm and Git. From the repository root in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Set-Location frontend
npm ci
npm run dev
```

In a second terminal, from the repository root:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:5173/ and API docs at http://127.0.0.1:8000/docs. Linux/macOS use `python3`, `.venv/bin/python` and the same npm commands. Run one backend worker. The original fixture simulator is available at `/legacy`; its v1 API remains unchanged. The enhanced workbench uses `/api/v2`.

### Sponsor configuration

Copy `.env.example` to `.env` and set values privately. Fixture mode needs no data credentials. AI investigations require Nightshift and a serving local model. Configure `METERLESS_BASE_URL`, `METERLESS_TOKEN_FILE`, `METERLESS_MODEL` and a private `SENTRY_HMEM_DIR`.

For live data, start the supplied Zetaris stack without resetting volumes, set `ZETARIS_BASE_URL`, `ZETARIS_ORG_ID`, `ZETARIS_API_TOKEN` and `SENTRY_DATA_MODE=zetaris`. A live failure never silently substitutes fixtures. On the existing Windows setup, run `python -m scripts.bootstrap_local_zetaris` from `backend` with the project venv. This seeds namespaced demonstration objects and creates an expiring application key using the saved administrator configuration privately. See [Zetaris details](docs/ZETARIS_INTEGRATION.md).

The local demo key belongs to the administrator account; application SQL is read-only/allowlisted, but production requires separately scoped service credentials. Never commit `.env`, tokens, local databases or model files, and never put credentials in `VITE_` variables. Respect runtime admission failures instead of disabling memory protections.

## Verification

From `backend`, run `python -m pytest -q` with the repository venv. From `frontend`, run `npm run build`, `npx playwright install chromium` and `npm run test:e2e`. CI pins Node for real H-MEM tests and runs browser checks.

Live tests are opt-in with `ZETARIS_LIVE_TESTS=1` and `AGENT_LIVE_TESTS=1`. To measure a real model, run `python -m scripts.evaluate_submission --label unique-run-name --model local-runtime/qwen2.5-coder-3b-instruct` from `backend`. Each evaluation gets independent H-MEM storage and retains failures in its denominator.

See [readiness and executed evidence](docs/SUBMISSION_READINESS.md), [API v2](docs/API_V2.md) and [the narration/shot list](docs/DEMO_SCRIPT.md).

## Assumptions and limits

- Three primary suppliers, six one-SKU orders and three inventory records, with fictional GBP fees and a fixed evaluation date of 25 October 2026.
- FIFO allocation by promise date/order ID, and whole-order completion. Costs are incremental fees plus residual penalties. Transit, split delivery, taxes, cancellation and regular procurement are excluded.
- Best among three fixed policies, not global supply-chain optimization. Arrival ranges are source claims, not calibrated probabilities.
- SQLite and H-MEM support one local demonstration workspace, not public multi-user tenancy.
- Nightshift receipt signature fields are counted but not independently cryptographically verified.
- A model may fail or exhaust its budget. No accepted recommendation is released in that case.

## Submission

The application guides users through Choose a problem → Check options → Your answer. One screen is shown at a time; charts and evidence are optional. See the [guided UX verification](docs/GUIDED_UX.md).

The final narrated MP4 follows the UI pass. Add video and deck URLs after upload and anonymous-access verification. Confirm the team roster, repository access and disclosure text before the final HackOS submission. The working cutoff is **27 October 2026, 23:45 UTC**. No customer savings, production deployment or unexecuted tests are claimed.
