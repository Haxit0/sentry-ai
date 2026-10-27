# Sentry AI — Open Agent Hackathon 2026

Track 2: **The Agent That Can Explain Why**

**Local integration preview:** this branch includes the Nightshift/H-MEM agent
API and baseline/disrupted dashboard comparisons. Use **Run AI investigation**
to call the configured runtime; the simulator remains deterministic and uses
synthetic data. See [local setup and verification](docs/LOCAL_AI_PREVIEW.md).
The original shared-baseline descriptions below refer to the simulator path.

Sentry AI investigates supply-chain disruptions, estimates order impact and compares recovery strategies. This shared starter is a deterministic **synthetic-data What-If simulator**, not yet an autonomous agent. No external orders or systems are modified.

Select a supplier, introduce a delay, and compare accepting the delay, expediting shipping, or buying from an alternative supplier. The application allocates inventory by promised date, calculates hypothetical late-delivery penalties, ranks recovery options and returns evidence for its recommendation.

## Working baseline and architecture

- Python 3.11+, FastAPI and Pydantic API on port **8000**.
- React, TypeScript and Vite dashboard on strict port **5173**.
- Three synthetic suppliers, six orders and three inventory SKUs.
- Fixed evaluation date **2026-10-25**; exact Python financial arithmetic, without an LLM.
- Typed API, provenance, validation, pytest suite and GitHub Actions.
- Explicit `fixture` execution mode and `not_configured` integration/agent status.

The known-answer scenario is `SUP-ALPHA` delayed five days: **£500.00** penalty exposure; **£160.00** expedited shipping is cheapest, saving **£340.00** against no action.

```text
React dashboard → Vite /api proxy → FastAPI → simulation service → fixture repository
                                                ↓
                                     evidence + ranked costs

Future: Zetaris data; Meterless Nightshift inference + an actual Meterless Engine
```

Read [architecture](docs/ARCHITECTURE.md), [the frozen contract](docs/CONTRACT.md), [ownership](docs/OWNERSHIP.md) and [the demo plan](docs/DEMO_PLAN.md) before coding.

## Install and run

Requirements: Git, **Python 3.11+**, **Node.js 22.12+** and npm. The fixture baseline needs no running Zetaris, Docker, WSL2, Nightshift, model download or credentials. Setup does not reconfigure those installations.

```bash
git clone https://github.com/Haxit0/sentry-ai.git
cd sentry-ai
```

macOS/Linux, or an already configured WSL shell, from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Windows PowerShell, from the repository root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a **second terminal**, from the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open [the dashboard](http://localhost:5173) and [interactive API documentation](http://localhost:8000/docs). Vite forwards `/api` to `127.0.0.1:8000`; keep both processes running. Port 3000 is reserved for the existing Zetaris setup. If port 5173 is occupied, Vite reports an error instead of silently selecting another port.

`.env.example` documents optional public frontend configuration and future integration settings. The baseline needs no `.env`. Vite can read root `VITE_API_BASE_URL` as a public backend origin; its blank default uses the dev proxy. Never put credentials in `VITE_` variables. The fixture backend does not read integration credentials or activate an adapter merely because settings exist. Never commit `.env`.

`npm run preview` serves the built frontend on 5173. A static deployment needs a reverse proxy for `/api` or an appropriate public `VITE_API_BASE_URL` at build time, plus backend CORS configuration for its actual origin. The two-terminal development setup above includes the proxy already.

## Tests and checks

With the repository virtual environment active:

```bash
cd backend
python -m pytest -q
```

PowerShell without activation, from the repository root:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest -q
```

From `frontend`:

```bash
npm run typecheck
npm run build
```

Smoke-test the running API:

```bash
curl http://127.0.0.1:8000/api/health
curl -X POST http://127.0.0.1:8000/api/simulations \
  -H 'Content-Type: application/json' \
  -d '{"supplier_id":"SUP-ALPHA","delay_days":5}'
```

PowerShell equivalent:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/simulations -Method Post -ContentType application/json -Body '{"supplier_id":"SUP-ALPHA","delay_days":5}'
```

GitHub Actions runs backend tests and frontend checks on pushes and pull requests. Inspect the current commit's actual workflow results; a workflow file alone is not proof that checks passed.

The shared baseline passed 40 backend tests and the frontend production build locally. See [the executed verification record](docs/VERIFICATION.md) for versions, live API/browser checks and limitations.

## Dataset and financial assumptions

All records and costs in `backend/app/data/demo_data.json` are hypothetical. Each order contains one SKU. On-hand stock goes to the earliest promised order first. An order completes only when all units arrive; uncovered units wait for the supplier's replenishment. Partial intervention capacity does not magically complete an order. Penalties are a flat daily fee per whole late order, not a fee per unit.

Estimated cost is **residual penalties + incremental recovery fees**. Regular procurement costs are common to the options and excluded. Alternative sourcing includes its configured premium. Exposure is not revenue loss, and a simulated recommendation does not execute a real purchase or shipment. See [the calculation assumptions](docs/ARCHITECTURE.md).

## Three-person collaboration

| Developer | Branch | Primary scope |
| --- | --- | --- |
| 1 | `feature/zetaris-data` | Data repository, Zetaris, source validation and provenance |
| 2 | `feature/agent-recovery` | Recovery, Nightshift, agents and a real Meterless Engine |
| 3 | `feature/whatif-dashboard` | React dashboard, What-If controls, evidence UX and demo |

After cloning, select your branch and pull its published shared baseline:

```bash
git fetch origin
git switch feature/zetaris-data # substitute your assigned branch
git pull --ff-only
```

For work already started, commit or stash your own changes, fetch, then merge `origin/main` deliberately. Do not reset teammates' changes or force-push. Open PRs to `main`, request a teammate review and run checks before merging. **Agree as a team before changing the frozen API** in `docs/CONTRACT.md` and `backend/app/schemas.py`. See [ownership and merge rules](docs/OWNERSHIP.md).

This repository is private. Add teammates under GitHub **Settings → Collaborators** if they cannot clone it. Never commit secrets, virtual environments, `node_modules`, model weights, downloaded data or installation files.

## Planned sponsor integrations

- **Zetaris — pending:** authenticated read-only federation across at least two real sources with provenance and explicit failures. See [issue #1](https://github.com/Haxit0/sentry-ai/issues/1).
- **Meterless Nightshift — pending:** real model discovery/inference and Planner, Investigator and Evaluator agents with evidence validation. See [issue #2](https://github.com/Haxit0/sentry-ai/issues/2).
- **Meterless Engine — pending:** at least one working Engine used in the workflow and demonstrated with reproducible tests. Provider configuration alone does not satisfy this.
- **NVIDIA Nemotron — not connected:** consider it after a real inference path works; do not claim its use without a model receipt proving it.
- **Dashboard evolution — pending:** richer evidence and actual execution traces when agents exist. See [issue #3](https://github.com/Haxit0/sentry-ai/issues/3).
- Use Claude Code, Cursor or the team's preferred tools, and record development tools and pre-existing components honestly.

Adapter placeholders report `not_configured`; they never fabricate success or silently substitute fixtures on a live integration failure.

## Submission planning

[Issue #4](https://github.com/Haxit0/sentry-ai/issues/4) records the team's target as **27 October 2026, 23:45 UTC**. Verify the deadline and requirements in the official event portal. Prepare the repository, a real 1–4 minute video, slides, sponsor explanation and pre-existing components disclosure. Sponsor integrations and autonomous investigation remain implementation work.
