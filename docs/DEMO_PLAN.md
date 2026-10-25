# Demonstration plan

Target: a 2–3 minute demonstration of the fixture baseline. Keep the synthetic disclaimer visible. Actual Zetaris, Nightshift, agents, Meterless Engine and NVIDIA integration are pending.

## Rehearsal

1. Install from a fresh checkout using the README. Run pytest, TypeScript checks and the production build.
2. Start FastAPI on 8000 and Vite on 5173. Confirm health reports `fixture` and integrations `not_configured`.
3. Select `SUP-ALPHA`; verify the evaluation date is 2026-10-25.
4. Keep API docs ready to inspect real requests and evidence. Hide terminals containing credentials in recordings.

## Shot list

| Time | Action | Explain |
| --- | --- | --- |
| 0:00–0:20 | Show Sentry AI and disclosure | Supply-chain investigation foundation for Track 2; deterministic simulator today |
| 0:20–0:45 | Alpha, delay 0, run | No disruption: no late orders or exposure; accepting baseline costs £0 |
| 0:45–1:20 | Alpha, delay 5, run again | Earliest orders receive stock; replenishment-dependent orders produce £500 penalties |
| 1:20–1:55 | Inspect orders, recovery ranking and evidence | Expedite costs £160 with no residual penalty, saving £340; compare alternative sourcing and no action |
| 1:55–2:20 | Try another supplier or delay | Results come from FastAPI calculations; lead times, capacities and fees constrain interventions |
| 2:20–2:45 | Show architecture/roadmap | Next: live Zetaris evidence, Nightshift agents and a real Meterless Engine |

Let requests finish and rerun after changing controls so the result matches the scenario. Never present an old result as a newly computed one.

## Explain the golden numbers

Alpha has ten on-hand units, satisfying `ORD-1001`. The twenty-unit `ORD-1002`, promised 27 October, waits until 1 November under a five-day disruption. Five late days at £100 per whole order per day produce **£500.00**. Expediting those twenty units to 27 October costs **£100 fixed + 20 × £3 = £160.00**. Alternative supply costs **£100 + 20 × £8 = £260.00**. Show evidence IDs, dates, capacities and assumptions. Penalty exposure is not revenue loss.

The fixture is hypothetical. Do not call it live business data, call an evidence list an agent trace, or claim a purchase/shipment was executed.

## Failure rehearsal

Optionally stop only this project's backend and run a simulation to verify an actionable dashboard error. Restart only that backend process using the README. Leave Docker, WSL2, Zetaris and Nightshift untouched. During judging, follow the working path and disclose actual failures plainly.

## Submission assets and next milestones

- Screenshots: normal scenario, Alpha disruption, ranked recoveries and evidence.
- Slides: problem, architecture, deterministic financial model, actual sponsor integrations/receipts, measured results, limitations and ownership.
- Keep three known-answer scenarios; add missing/conflicting evidence and actual agent recovery when implemented.
- Record the final integrated application, not a mockup. The current starter has no real sponsor call or agent execution to show.
- [Issue #4](https://github.com/Haxit0/sentry-ai/issues/4) records 27 October 2026, 23:45 UTC as the submission target. Verify in the official portal; prepare the repository, 1–4 minute video, slides and disclosures.
