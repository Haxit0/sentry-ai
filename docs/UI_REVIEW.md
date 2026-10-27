# Earlier UI checkpoint — 27 October 2026

Superseded by the [guided task flow](GUIDED_UX.md) after user usability feedback.

The workbench now follows three visible steps: **Scenario → Investigation → Decision**. Desktop navigation and a sticky three-step bar lead to the same sections. The phone layout keeps the three-step bar and a history button; no side drawer is required for the main task.

The top-left brand is the Sentry AI wordmark. Decorative shields were removed from the brand and explanatory content after user review. Meaningful validation checks remain.

## What changed

- Clear primary AI investigation action, with a separate calculation-only preview.
- Optional spending and lateness constraints are collapsed until needed; the constrained preset opens them.
- Supplier context shows real retrieved records and labels the delay as a hypothetical assumption.
- Real event timeline and agent stages; rejected drafts, source receipts and memory details stay expandable.
- A single decision view avoids duplicated results. Calculated and AI results can be selected explicitly.
- Recovery cards separate intervention cost, residual penalties and remaining lateness.
- An interactive 0–30 delay chart uses backend results. Exploring it never changes the operator's scenario. Infeasible intervals are not connected as though a policy were feasible.
- Recorded inputs remain attached to results. Editing controls shows a stale-result warning.
- Searchable run-history dialog supports Escape and native modal focus behavior. Previous-run comparison retains separate evidence snapshots.
- Human review is shown with the investigation result, so a calculated preview cannot be confused with the recommendation being approved.
- Downloads and technical detail are available on demand. Errors remain visible even when the operator is reviewing a lower section.
- Keyboard focus styles, reduced motion, 44px primary actions and layouts checked at 1440, 768, 375 and 320 pixels.

## Executed verification

- **30 browser tests passed** in one combined run, including the original simulator tests and the enhanced navigation checks.
- **180 backend tests passed; 3 opt-in live tests skipped.** Live services were exercised separately.
- Typecheck and production build passed. No new application dependency was introduced.
- A real redesigned-browser investigation `run-be596e134557` validated Alpha +5 using five Nightshift calls, five returned receipt envelopes and three recalled H-MEM findings. Exposure GBP 500.00; expedited recovery GBP 160.00. Receipt envelopes are not independently cryptographically verified.
- Final wordmark cleanup is cosmetic and follows that live run. No backend or API contract was changed by this pass.

## Visual evidence

[Desktop scenario](evidence/ui-scenario-desktop.png) · [Desktop decision](evidence/ui-decision-desktop.png) · [Phone decision](evidence/ui-decision-mobile.png). These views use real deterministic API calculations. [Final local workspace](evidence/ui-workspace.png) shows the plain wordmark.

The deck's test count records the earlier functional checkpoint. Refresh final presentation screenshots and totals during the recording/package pass. The final narrated video, uploaded links and HackOS confirmation remain outstanding.
