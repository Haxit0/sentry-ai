# Narration and recording plan

Target: 3 minutes 15 seconds, 1080p, 16:9, with clear human narration. Final recording follows the
UI pass. Keep the synthetic-data disclosure visible.

| Time | Screen and narration |
| --- | --- |
| 0:00–0:20 | Title and problem. “Sentry AI is our entry for The Agent That Can Explain Why. A supply-chain planner receives a supplier delay. Orders, stock and recovery quotes are scattered across systems. They need a decision they can explain.” |
| 0:20–0:40 | Cases and constraints. “Sentry investigates evidence, compares recovery choices and shows what would change the recommendation. These are synthetic records, accessed through real PostgreSQL and CSV connectors in Zetaris.” |
| 0:40–1:15 | Architecture and authentic feedback trace. “The Planner chooses questions, the Investigator gathers facts and a model Critic challenges the explanation. Our deterministic Evaluator checks figures and citations. Evidence gaps return to the Planner. Here is that exchange in the recorded trace.” |
| 1:15–2:00 | Real Alpha +5 run. “Stock covers the first order, leaving ORD-1002 late. The calculated exposure is five hundred pounds. Every model call runs through Nightshift. We may shorten the waiting in this recording, but these are the actual inputs and output.” |
| 2:00–2:25 | Provenance and receipts. “Zetaris joins PostgreSQL orders with supplier CSV records and retrieves carrier updates. These query IDs identify the work. Nightshift receipts identify the served model, accelerated locally with NVIDIA CUDA on our RTX 4080.” |
| 2:25–2:50 | Recovery comparison. “Expediting totals one hundred and sixty pounds. At seven days the preferred policy changes to alternative sourcing. A fifty-pound budget and zero late days leave no feasible recovery. These figures are calculated exactly.” |
| 2:50–3:15 | Memory, uncertainty and export. “H-MEM recalls prior findings but every current amount is rechecked. When supplier and carrier estimates disagree, Sentry withholds a firm recommendation. The planner receives evidence, limitations and an exportable decision packet for human review.” |

## Recording checks

- Confirm all sponsor services and a model lane are ready before recording.
- Show an actual feedback exchange. If the main run needs no retry, use an authentic recorded run,
  labelled as recorded. Never present a scripted test as live agent collaboration.
- Hide `.env`, credentials, raw headers and key pages. Show query IDs and sanitized receipts instead.
- Record the final output and audible narration. Keep the video between one and four minutes.
- Export `OAH2026-SentryAI-ExplainWhy-Demo.mp4`. Keep local, backup and team copies.
- Test uploaded playback and audio without account permissions before linking it from the README.

## Impact measurement

Optionally time a human reproducing the Alpha calculation from exported rows, then compare with a
real Sentry run. Record the task definition and sample size. Without that measurement, describe the
reduced source-switching qualitatively; do not invent minutes saved or a productivity percentage.
