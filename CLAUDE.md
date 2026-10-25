# Working on Sentry AI

Read README and `docs/OWNERSHIP.md`, `docs/CONTRACT.md`, `docs/ARCHITECTURE.md` first. These conventions apply to Claude Code, Cursor and other coding assistants.

## Boundaries

- This is a deterministic synthetic simulator, not yet an autonomous agent. Keep `fixture`, `not_configured` statuses and disclosure honest.
- API/schema contracts are frozen. Obtain team agreement before changes; update models, frontend types, docs and tests together afterward.
- Respect file/branch ownership. After the initial scaffold, use assigned feature branches and PRs. Preserve legitimate work and never force-push shared branches.
- Do not modify, restart or reconfigure Docker, WSL2, Zetaris or Nightshift.

## Conventions

- Python 3.11+, typed FastAPI/Pydantic, React/TypeScript/Vite. Keep dependencies minimal.
- Data retrieval belongs in `app/data`; deterministic algorithms in `app/services`; external transport in `app/integrations`.
- Use exact Python arithmetic for money, never binary floats or LLM calculations. Preserve two-decimal GBP strings at the API boundary.
- Pin fixture evaluation to 2026-10-25. Keep known-answer tests free of system date, randomness and network calls.
- Allocate by promised date with deterministic ties; respect capacity and lead times, preserve residual shortfalls and expose assumptions.
- Preserve evidence/provenance. Unknown supplier is 404; invalid request is 422. Future explicit live mode must never silently fall back on integration failure.
- Placeholder adapters report `not_configured`; never fabricate responses, inference receipts, traces or sponsor success.
- Never commit secrets, `.env`, environments, `node_modules`, models, downloads or installation files; never log tokens.

## Validation

From `backend` using the repository virtual environment: `python -m pytest -q`.

From `frontend`: `npm run typecheck` and `npm run build`.

For API/UI changes, run the real application. Alpha +5 must return £500 exposure and £160 expedite as cheapest; zero delay must show no exposure. Check applicable error/no-impact states. Report only executed checks.

Use backend 8000 and frontend strict 5173, avoiding Zetaris 3000. Keep README commands/status accurate and document material assumptions. A teammate reviews feature PRs before merge.
