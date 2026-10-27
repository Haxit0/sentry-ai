# Guided task flow

The default experience is now a three-screen task, replacing the dense dashboard. Only the active screen is rendered.

1. **Choose a problem.** Three plain-language situation cards and one Continue button. Other examples are optional.
2. **Check options.** The question matches the chosen situation. Late deliveries ask about delay, budget cases ask about spending and lateness limits, and conflicting arrival reports show the actual supplier/carrier estimates from the data source. One primary action starts the AI check. An optional order list shows which customers are being checked.
3. **Your answer.** One next action, its total estimated cost, the comparison with doing nothing and remaining lateness. Source disagreements or infeasible constraints lead with the human question or limits that need changing. AI and calculation-only previews are clearly distinguished.

Charts, options, agent events, model receipts, memory and evidence are available only when requested. The left sidebar, large introductory copy, integration banner, stacked empty sections and competing primary actions have been removed. Plain Sentry AI branding is retained.

During a real AI check the current task shows activity, allows cancellation and advances to the answer when complete. If the operator leaves the waiting screen, completion does not force them back. Approval records a choice; it does not purchase or ship anything. Past checks remain accessible from the header.

## Executed verification

- 28 browser checks passed together: 16 original simulator/agent compatibility checks and 12 guided-flow checks.
- Covered a clear first visit, optional detail, exact cost preview, infeasible constraints, conflicting sources, plus/minus controls, independent chart exploration, cancellation, searchable keyboard-dismissible history, source failure and 1440/768/375/320px layouts.
- Typecheck and production build passed. Backend/API behavior was preserved.
- A real browser flow completed and automatically showed a validated answer; [live metadata](evidence/guided-live-check.json) records actual Nightshift calls, Zetaris acquisition and H-MEM recall.

[Desktop start](evidence/guided-start-desktop.png) · [Phone start](evidence/guided-start-mobile.png) · [Real AI answer](evidence/guided-answer.png).

[Budget screen](evidence/guided-budget.png) · [Source disagreement screen](evidence/guided-arrival-reports.png) · [Final starting screen](evidence/guided-start.png). The More examples control is explicitly sized and styled as a readable secondary action.

The previous UI review is an earlier checkpoint. Final narration, deck screenshots and submission links must use this guided version.
