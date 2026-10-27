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
Startup was refused by Nightshift with `admission_paused: memory pressure
critical`; its report showed about 10 GB of swap in use. Resource protection
was preserved. A real `POST /api/investigations` returned HTTP 503 because no
model was serving. No successful live inference or validated AI report has
been observed on this PC yet. Close unused heavy applications and start the
local lane in Nightshift, then retry the dashboard investigation.
