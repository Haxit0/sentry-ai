# Submission readiness â€” 27 October 2026

The functional sponsor chain is verified locally. Final submission remains **incomplete** until the narrated video, team confirmation and judge-facing links are complete. The UI pass is complete; see [UI review](UI_REVIEW.md). The working deadline is 27 October, 23:45 UTC. No winning outcome is guaranteed.

## Requirement audit

| Requirement | Status | Evidence / practical limit |
| --- | --- | --- |
| Existing data branch merged; dashboard and v1 preserved | Verified | Git merge history; `/legacy`; compatibility browser tests |
| Zetaris deployment/configuration preserved and authenticated | Verified | [Clean live check](evidence/clean-setup-live.json); existing Docker volumes retained |
| PostgreSQL orders joined with supplier/inventory CSV; carrier CSV | Verified | Four real query IDs and source names in [final packet](evidence/final-live-decision-packet.json) |
| Explicit fixture/live resolver; live failures never fall back | Verified | `app/v2/data.py`; `test_live_mode_never_falls_back` |
| Synthetic data and acquisition provenance | Verified | SHA256, source/query IDs, rows, acquisition interval in packet; no atomic cross-source consistency claimed |
| Additive v2 API, dashboard types and API documentation | Verified | [API v2](API_V2.md), typed workbench, legacy tests |
| Decimal costs, constraints, capacity and tie behavior | Verified | Alpha +5: exposure GBP 500.00, expedite GBP 160.00; zero-delay, limited-capacity and infeasibility tests |
| Pinned 0â€“30 delay sweep, selected alternative and uncertainty bounds | Verified | Same snapshot throughout; Alpha preferred policy changes at +7 days; hypothetical assumptions labelled |
| Nightshift sole application AI provider; H-MEM memory engine | Verified | Final packet: actual model, three fresh calls, receipts and stored memory |
| 3B versus 7B live selection alongside Zetaris | Verified | [Selection](evidence/model-selection.json); [3B](evidence/qwen3b-final-fresh.json) 9/9 expected outcomes, 5.913s median; [7B](evidence/qwen7b-final-fresh-serving.json) 8/9, 11.773s |
| NVIDIA contribution | Verified | CUDA inference on RTX 4080 Laptop GPU; local Qwen, no Nemotron claim or NVIDIA API key requirement |
| Planner â†’ Investigator â†’ Critic â†’ deterministic Evaluator | Verified | Actual events, tools, critiques and rejected drafts; feedback can revise tools; targeted routing unit test |
| Bounded attempts/calls/tools/deadline, cancellation and queue | Verified | Three drafts, eight model calls, 32 tools, 120-second processing limit; one worker plus two queued; cancellation tests |
| Contradictions, stale evidence, invalid claims/citations and injected text | Verified | Conflicting/stale cases withheld; evaluator veto tests; source instructions do not expand tool access |
| H-MEM provenance, recalculation, feedback and conflicts | Verified | Current amounts recalculated; only validated conclusions saved; memory/feedback details visible |
| Matched cold/warm evaluation | Verified | [Two paired runs](evidence/memory-comparison.json); no speed advantage demonstrated; sample too small for broad claims |
| SQLite traces, history/comparison, exports and human review | Verified | Local run storage; comparison preserves each snapshot; approval records no external action |
| Clean setup and independent state | Verified | Committed Git archive 45232a4, fresh venv/npm install, 180 passing backend tests and frontend build; live sponsor check with isolated H-MEM |
| CI: Node for H-MEM and browser tests | Verified | [All remote code checks passed at 45232a4](evidence/github-checks.json); final documentation commits may trigger another run |
| Credential scan: working tree and all reachable history | Verified | [Security scan summary](evidence/security-scan.json); redacted Gitleaks scan; secret values excluded |
| README, Track 2 description, disclosures | Verified | [README](../README.md), [description and disclosures](PROJECT_DESCRIPTION.md); Cursor unconfirmed, not claimed |
| Eight-slide editable deck and PDF | Verified | [PPTX](../submission/Sentry_AI_Submission_Deck_Final.pptx), [PDF](../submission/Sentry_AI_Submission_Deck_Final.pdf); package/layout checks and visual PDF review |
| 3:15 narration script and functional shot list | Verified | [Demo script](DEMO_SCRIPT.md); show real feedback, queries, calls, memory and decision |
| Final visual redesign | Verified | [UI and navigation review](UI_REVIEW.md); responsive layouts and 30 browser tests |
| Final narrated 1â€“4 minute MP4, audio, primary/backup copies | Incomplete by agreed sequencing | Record together after UI pass; user narration; no finished recording is claimed |
| Anonymous judge-facing video/Drive links | Incomplete | Upload and test without account permissions after recording |
| Official HackOS roster, track, repository access and final submission | Incomplete | Human confirmation and final HackOS action required |

Published review: [GitHub PR #8](https://github.com/Haxit0/sentry-ai/pull/8). No merge or final HackOS submission has been performed.

## Final local verification

- Backend: **180 passed, 3 opt-in live checks skipped**; live sponsor checks were run separately.
- Browser: **30 passed** using installed Chrome; production build and typecheck passed.
- Release confirmation after final provenance storage: [9/9 expected outcomes, 6.084s median](evidence/qwen3b-release-provenance.json), with recall on the repeated case. The deck retains the original matched model-selection comparison.
- Acceptance calculations: [all eight cases](evidence/acceptance-cases.json).
- Matched memory test: cold median **5.959s**, warm median **6.575s**, two pairs; recall worked but no speed gain.

## Measured scope and limitations

Nine fixed checks include eight named cases plus one repeated Alpha case. Correct behavior includes *withholding* advice for budget/deadline infeasibility, conflicting arrivals and stale updates. Six validated outputs plus three intended unresolved outputs are not a general accuracy or reliability claim. The model context limits differed to fit this machine (3B 8192, 7B 4096). Both used the same case order, fresh H-MEM stores and per-request Nightshift cache scopes. Failed early experiments were retained locally, including strict JSON mode refusing code-fenced answers. A mistaken attempt to query a stopped 7B lane returned explicit failures and was rerun only after its lane started; it is not included as a serving-model benchmark.

The selected 3B model remains configured locally; 7B is installed as a stopped comparison lane. Runtime memory admission remains enabled. A future startup may wait for memory; failures are visible. Receipt envelopes are retained but not independently cryptographically verified.

The fixed evaluation date is 25 October 2026. All records, reported arrival dates, costs and constraints are synthetic. This is a local single-workspace prototype with three fixed recovery policies. Production tenancy, independently scoped service credentials, customer evidence and measured operational impact remain outside this submission. The local application key is administrator-owned; application queries are read-only/allowlisted. No purchases, shipment bookings, supplier contact or realized savings are claimed.

## Recording sequence

Start with Alpha +5, show GBP 500 exposure and GBP 160 expedited recovery. Expand the actual collaboration trace and rejected drafts; if necessary use the authentic recorded feedback case explicitly labelled recorded. Show the Zetaris query IDs, Nightshift model/receipts and H-MEM recall. Change the delay to +7; then show impossible constraints and conflicting source arrival claims. Export the packet and show human review. Preserve any time compression visibly.

The deck and repository must match the final recorded version. Do not label the build submitted until the video and access checks are complete.
