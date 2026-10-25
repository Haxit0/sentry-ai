# Ownership and parallel development

The initial scaffold lives on `main`. Each developer starts from the published shared baseline on an existing feature branch. No branch containing independent work is force-updated.

| Developer | Branch | Primary files | Responsibilities |
| --- | --- | --- | --- |
| 1 — Data and Zetaris | `feature/zetaris-data` | `backend/app/data/`, `backend/app/integrations/zetaris.py`, data/integration tests | Zetaris integration, fragmented datasets, real bounded queries, validation and provenance, integration tests |
| 2 — AI and recovery | `feature/agent-recovery` | `backend/app/services/`, `backend/app/integrations/meterless.py`, recovery/agent tests | Nightshift, Planner/Investigator/Evaluator agents, at least one real Meterless Engine, recovery algorithms, validation, evidence-backed explanations and execution traces |
| 3 — Frontend and What-If | `feature/whatif-dashboard` | `frontend/`, `docs/DEMO_PLAN.md` | Dashboard, disruption controls, recovery comparisons, evidence visualisation, UX and demo preparation |

## Shared boundaries

`docs/CONTRACT.md`, `backend/app/schemas.py`, `backend/app/main.py`, dependency files, CI and root documentation are shared. The API contract is frozen for parallel development. Discuss changes with all three developers before implementation, including names, types, status meanings, currency encoding and errors. After agreement, update backend models, frontend types, contract and tests together.

- Developer 1 provides typed records through the repository boundary. Simulation must not depend on Zetaris transport details.
- Developer 2 preserves deterministic finance and fixture tests. Agents explain or verify computed values; they never replace them with generated arithmetic.
- Developer 3 consumes the actual endpoints and disclosure fields. Do not manufacture integration status or traces in the dashboard.
- Fixture mode stays independently runnable. A future explicit live mode reports unavailable integrations and never silently falls back on an error.
- Coordinate changes to the shared golden scenario and `test_simulation.py`.

## Start a clean checkout

```bash
git clone https://github.com/Haxit0/sentry-ai.git
cd sentry-ai
git fetch origin
git switch feature/zetaris-data # or feature/agent-recovery / feature/whatif-dashboard
git pull --ff-only
```

Follow the root README for isolated Python and frontend dependency setup. No developer needs another developer's unfinished integration to run the fixture baseline. Use ports 8000 and 5173; leave Zetaris port 3000 alone.

## Update an existing working branch

Commit or stash your own changes first. Preserve any legitimate work already on the branch.

```bash
git fetch origin
git switch feature/zetaris-data # your branch
git pull --ff-only
git merge origin/main
# Resolve conflicts deliberately, run checks, then:
git push origin HEAD
```

If a feature branch gained independent changes before scaffold publication, the publisher leaves it intact. Its owner merges `origin/main` using this workflow. Never reset or force-push the branch to match `main`.

## Pull requests and integration

Open PRs to `main`. Keep scope small, describe concrete behavior, include executed validation, and have another teammate review. Run backend tests and frontend checks. Do not merge API changes without team agreement. Rotate integration reviewer daily and coordinate on [issues #1–#4](https://github.com/Haxit0/sentry-ai/issues).

Never commit secrets, `.env`, virtual environments, `node_modules`, model weights or installation files. Do not modify, restart or reconfigure Docker, Zetaris, WSL2 or Nightshift as part of normal application work.
