# Sentry AI — Open Agent Hackathon 2026

Track 2: **The Agent That Can Explain Why**

Sentry AI investigates simulated supply-chain disruptions, estimates order impact and compares recovery strategies. The **current starter** is a deterministic, synthetic-data What-If simulator — **not yet an autonomous agent**. It ships as a shared baseline so three developers can work independently.

## Architecture and collaboration

Read `docs/OWNERSHIP.md`, `docs/CONTRACT.md`, `docs/ARCHITECTURE.md`, and `docs/DEMO_PLAN.md` before coding.

## Requirements

Python 3.11+, Node.js 20+, npm, Git. No running Zetaris/Nightshift required to run the fixture baseline.

## Run from WSL2

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a **second** terminal, from the repository root:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and run the simulator. Back-end docs: http://localhost:8000/docs.

**Test:**

```bash
source .venv/bin/activate
cd backend
python -m pytest -q
```

## Dataset assumptions

Synthetic records in `backend/app/data/demo_data.json`; dates are pinned to 2026-10-25 for repeatability. This is **not live market data**. Warehouse on-hand stock is allocated to orders by earliest promised date, and any uncovered order units are assumed to arrive on the supplier restock date. Interventions have hypothetical lead times, capacity and fixed/variable fees. Estimated penalty exposure is the sum of contractual hypothetical daily penalties on orders estimated late. This is not actual revenue loss, nor an operational recommendation for real customers. No external orders are modified.

## GitHub team setup

Private repo `Haxit0/sentry-ai`. Add the other two people as collaborators under **Settings → Collaborators**. Work from `main` on branches `feature/zetaris-data`, `feature/agent-recovery`, or `feature/whatif-dashboard`. Open pull requests, have a teammate review, and run tests before merging. See `docs/OWNERSHIP.md`.

```bash
git clone https://github.com/Haxit0/sentry-ai.git
cd sentry-ai
git switch feature/zetaris-data   # or your assigned branch
```

Do **not** commit local secrets, model weights, downloaded data or your Zetaris installation.

## Sponsor status

- Zetaris: **integration pending** in this repository; production adapter placeholder present.
- Meterless Nightshift: **integration pending** in this repository; adapter placeholder present.
- Meterless Engine: **integration pending**. Must work in a real feature before submitting.
- NVIDIA Nemotron: **not connected**; NVIDIA account may still be blocked. Do not claim its award without real inference evidence.
- Cursor / Claude Code: use your preferred tool and record how you built the project.

## Deadline

27 October 2026, 23:45 UTC — verify with the official event portal. Include repository, 1–4 minute video, slide deck, sponsor explanation and pre-existing components disclosure.
