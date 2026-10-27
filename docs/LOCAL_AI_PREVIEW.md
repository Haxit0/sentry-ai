# Local AI integration preview

This branch combines `origin/feature/agent-recovery` at `426f71d` and Simon's
`origin/feature/whatif-dashboard` at `b61ebdf`. It adds a dashboard entry point
for the existing additive `POST /api/investigations` API. Main and the shared v1
simulation contract are unchanged.

Open http://127.0.0.1:5173/, choose a supplier and delay, then use:

- **Run simulation** for deterministic baseline/disrupted comparisons.
- **Run AI investigation** for Nightshift planning and explanation, evidence
  tools, deterministic validation, and Meterless H-MEM recall/write-back.

The AI panel shows only a validated recommendation. An unresolved response
shows the reasons for rejection; runtime failures show an error. There is no
fallback AI answer. Changing supplier or delay clears the AI report and aborts
the browser wait. That does not cancel an investigation already running on the
server, which may finish and save validated memory. The browser waits up to
four minutes, separately from the simulator's 15-second request timeout.

Data remains synthetic fixtures. The Zetaris feature branch is not included
in this preview. The v1 health/response `agent_status: not_configured` describes
the deterministic simulation endpoint; the separate investigation report carries
its actual model, receipts, validation and memory status.

## Local runtime

Nightshift Windows 1.2.7 was installed from Meterless's official Windows
download. The installer SHA-256 matched its published checksum:
`f30cfc10fed2510b7820c512e4ea78459967670e0a5fb2c7af9d68b4b5f03d3a`.

The ignored root `.env` points at `http://127.0.0.1:8088/v1`, requests
`meterless/local`, and references Nightshift's existing `proxy-token` file.
No credential value is copied into the repository. H-MEM persists under
the ignored `local_data/hmem` directory. Nightshift and its downloaded model
must be available for real inference; fixture simulation works independently.

## Executed validation

- Integrated backend: 102 passed, 3 skipped (live tests), Python 3.14.
- Frontend: TypeScript and production build passed.
- Browser checks: 13 comparison tests and 3 AI-panel tests passed against the local
  FastAPI and Vite servers with installed Chrome. Includes real simulation comparisons plus explicitly mocked
  AI transport failures/unresolved reports; those transport tests do not prove
  live inference. Live runtime results must be recorded separately.

No changes were pushed to GitHub by this integration task.

## Live check on this PC

Nightshift 1.2.7 responds to its official CLI status check. The catalogued
Qwen2.5-Coder-3B-Instruct-Q4_K_M model was downloaded (1,929,903,360 bytes).
The dedicated `sentry-qwen3b` lane uses an 8192-token context and one slot.
Startup was initially refused because Windows lacked available commit memory.
After unused applications were closed, normal startup succeeded without changing
resource protections. The lane reports `ready` with full placement on CUDA0,
the NVIDIA RTX 4080 Laptop GPU.

Two real Alpha +5 investigations passed on 27 October 2026:

- API run `inv-d840b7566c56`: HTTP 200 in 11 seconds, validated on the first
  draft; expedite shipping GBP 160.00 against GBP 500.00 exposure. Two model
  calls returned two signed receipts. H-MEM saved `mem-1`.
- Dashboard run `inv-e1a5f7f2cb7b`: validated on the first draft; the same
  calculated recommendation, two model calls and two signed receipts. H-MEM
  recalled one prior finding and saved the new validated finding.

Both reports identify `local-runtime/qwen2.5-coder-3b-instruct` as the model.
The first full report is saved only in ignored `local_data/`.
These are real inference and memory operations over synthetic fixture data;
they do not verify live Zetaris integration or all possible scenarios.
