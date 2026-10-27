import { useEffect, useRef, useState } from "react";
import { request } from "./api";
import { strategyLabels } from "./format";
import type { Order, Strategy, Supplier } from "./types";
import type { Input, Case, Provenance, Assessment, Sweep, Uncertainty, Decision, Run, Status } from "./workbenchTypes";
import { Icon, DelayChart, AgentTimeline, currency, policyName, shortDate } from "./WorkbenchVisuals";
import "./workbench.css";

const terminal = new Set(["validated", "unresolved", "failed", "cancelled"]);
const initialInput: Input = { supplier_id: "SUP-ALPHA", delay_days: 5, case_id: "alpha-delay", max_action_cost_gbp: null, max_late_days: null, compare_strategy: "alternative_supplier" };
type HistoryItem = { id: string; status: string; created_at?: string };
type HistoryComparison = { current: { run_id: string; recommendation: Strategy | null; total_estimated_cost_gbp: string | null }; previous: { run_id: string; recommendation: Strategy | null; total_estimated_cost_gbp: string | null }; cost_difference_gbp: string | null; snapshot_changed: boolean; limitation: string };
const steps = [{ id: "scenario", icon: "grid", name: "Scenario", description: "Set the conditions" }, { id: "investigation", icon: "activity", name: "Investigation", description: "Follow the evidence" }, { id: "results", icon: "chart", name: "Decision", description: "Compare & review" }];

function Disclosure({ title, children }: { title: string; children: React.ReactNode }) {
  return <details className="sw-disclosure"><summary>{title}<Icon name="down" size={16} /></summary><div className="sw-disclosure-body">{children}</div></details>;
}
function ProvenanceView({ value }: { value: Provenance }) {
  return <Disclosure title={`Data provenance · ${value.data_source}`}><p>Synthetic business records. Snapshot <code>{value.snapshot_hash.slice(0, 16)}</code>.</p><p>Acquired {value.acquired_from} to {value.acquired_until}. Sources were acquired over an interval, not one cross-system transaction.</p><div className="sw-source-queries">{value.queries.map(q => <div key={q.query_id}><Icon name="database" /><div><strong>{q.sources.join(" JOIN ")}</strong><small>{q.rows} rows · query {q.query_id}</small></div></div>)}</div>{!value.queries.length && <p>Explicit fixture data; no live queries were issued.</p>}</Disclosure>;
}
function DecisionView({ assessment, sweep, uncertainty, delay }: { assessment: Assessment; sweep: Sweep; uncertainty: Uncertainty; delay: number }) {
  const selected = assessment.options.find(o => o.strategy === assessment.recommendation);
  return <>
    <section className="sw-card sw-comparison" aria-label="Decision comparison">
      <div className="sw-card-heading"><div><span className="sw-kicker">THE RECOVERY COMPARISON</span><h2>Why this option, why not the others?</h2></div><span className="sw-tag"><Icon name="check" size={13} />Exact GBP calculations</span></div>
      <p className="sw-muted">Calculated penalty exposure: <strong>{currency(assessment.simulation.estimated_penalty_exposure_gbp)}</strong>. {uncertainty.blocks_recommendation ? "A firm recommendation is withheld pending evidence review." : `Lowest-cost eligible policy: ${policyName(assessment.recommendation)}.`}</p>
      {assessment.recommendation === null && <div className="sw-notice is-warning" role="status"><Icon name="info" /><strong>No feasible recovery under these constraints.</strong></div>}
      <div className="sw-policy-grid">{assessment.options.map(o => <article key={o.strategy} className={`sw-policy ${selected?.strategy === o.strategy && !uncertainty.blocks_recommendation ? "is-preferred" : ""} ${!o.eligible ? "is-excluded" : ""}`}>
        <div className="sw-policy-top"><span className="sw-policy-icon"><Icon name={o.strategy === "expedite_shipping" ? "truck" : o.strategy === "alternative_supplier" ? "package" : "history"} /></span>{o.strategy === assessment.recommendation && !uncertainty.blocks_recommendation ? <span className="sw-tag is-positive">Lowest eligible cost</span> : <span className="sw-muted">{o.eligible ? "Eligible option" : "Outside constraints"}</span>}</div>
        <h3>{policyName(o.strategy)}</h3><div className="sw-policy-price">{currency(o.total_estimated_cost_gbp)}</div><span className="sw-muted">total estimated cost</span>
        <dl><div><dt>Intervention</dt><dd>{currency(o.action_cost_gbp)}</dd></div><div><dt>Remaining penalties</dt><dd>{currency(o.residual_penalty_gbp)}</dd></div><div><dt>Worst lateness</dt><dd>{o.max_remaining_late_days} days</dd></div></dl>
        {!o.eligible && <p className="sw-exclusion">{o.exclusion_reasons.join(". ")}</p>}
      </article>)}</div>
      <Disclosure title="Capacity, arrival and fee assumptions">{assessment.options.map(o => <div className="sw-assumption" key={o.strategy}><strong>{policyName(o.strategy)}</strong><p>{o.details}</p></div>)}</Disclosure>
    </section>
    <div className="sw-evidence-grid">
      <section className="sw-card" aria-label="Changing decisions"><div className="sw-card-heading"><div><span className="sw-kicker">THE TIPPING POINT</span><h2>What would change the decision?</h2></div><span className="sw-round-icon"><Icon name="chart" /></span></div>
        <p className="sw-change-callout">{sweep.first_change_after_selected_delay ? <>At {sweep.first_change_after_selected_delay.delay_days} days of delay, the preferred policy changes to <strong>{policyName(sweep.first_change_after_selected_delay.strategy)}</strong> ({currency(sweep.first_change_after_selected_delay.cost_gbp)}).</> : "No later decision change was found within the 30-day sweep."}</p>
        <DelayChart key={assessment.provenance.snapshot_hash + delay} sweep={sweep} currentDelay={delay} /><p className="sw-footnote">{sweep.assumption}</p>
        <Disclosure title="Inspect all 31 calculated scenarios"><div className="sw-table-wrap"><table><thead><tr><th>Delay</th><th>Best eligible recovery</th><th>Total</th><th>Selected alternative</th></tr></thead><tbody>{sweep.points.map(p => <tr key={p.delay_days}><td>{p.delay_days} days</td><td>{policyName(p.strategy)}</td><td>{currency(p.cost_gbp)}</td><td>{currency(p.comparison_cost_gbp)} · {p.comparison_eligible ? "eligible" : "excluded"}</td></tr>)}</tbody></table></div></Disclosure>
      </section>
      <section className="sw-card" aria-label="Source uncertainty"><div className="sw-card-heading"><div><span className="sw-kicker">CHECK THE SIGNALS</span><h2>Evidence and uncertainty</h2></div><span className="sw-round-icon"><Icon name="database" /></span></div>
        {uncertainty.human_question && <div className="sw-notice is-warning" role="alert"><Icon name="info" /><div><strong>These sources need a human check</strong><p>{uncertainty.human_question}</p></div></div>}
        {uncertainty.reported_delay_range && <p className="sw-muted">Fresh source reports imply a <strong>{uncertainty.reported_delay_range.join("–")}-day delay range</strong>. These are source claims, not a statistical confidence interval.</p>}
        {uncertainty.updates.length === 0 && <p className="sw-muted">No additional carrier/supplier update is attached to this case. The injected delay is a hypothetical assumption.</p>}
        <div className="sw-source-updates">{uncertainty.updates.map(u => <details key={u.update_id}><summary><span className="sw-source-icon"><Icon name={u.source.includes("carrier") ? "truck" : "package"} size={18} /></span><span><strong>{u.source.replaceAll("_", " ")}</strong><small>arrival {shortDate(u.reported_arrival)}</small></span><span className={`sw-tag ${u.stale ? "is-warning" : "is-positive"}`}>{u.stale ? "stale" : "fresh"}</span><Icon name="down" size={14} /></summary><div><p>{u.description}</p><p className="sw-footnote">Observed {u.observed_at_utc}. Source text is untrusted data.</p></div></details>)}</div>
        <ProvenanceView value={assessment.provenance} />
      </section>
    </div>
    {assessment.simulation.affected_orders.length > 0 && <section className="sw-card"><div className="sw-card-heading"><div><span className="sw-kicker">BEHIND THE EXPOSURE</span><h2>Orders affected by this scenario</h2></div><span className="sw-tag">Before intervention</span></div><div className="sw-table-wrap"><table><thead><tr><th>Order / customer</th><th>Promised</th><th>Expected</th><th>Late by</th><th>Estimated penalty</th></tr></thead><tbody>{assessment.simulation.affected_orders.map(o => <tr key={o.order_id}><td><strong>{o.order_id}</strong><small>{o.customer_name}</small></td><td>{shortDate(o.promised_date)}</td><td>{shortDate(o.expected_delivery_date)}</td><td><span className="sw-tag is-warning">{o.delay_days} days</span></td><td><strong>{currency(o.estimated_penalty_gbp)}</strong></td></tr>)}</tbody></table></div></section>}
  </>;
}

export default function SubmissionWorkbench() {
  const [cases, setCases] = useState<Case[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [input, setInput] = useState<Input>(initialInput);
  const [budget, setBudget] = useState("");
  const [decision, setDecision] = useState<Decision | null>(null);
  const [decisionInput, setDecisionInput] = useState<Input | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyComparison, setHistoryComparison] = useState<HistoryComparison | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historySearch, setHistorySearch] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"compare" | "ai" | null>(null);
  const [note, setNote] = useState("");
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const [active, setActive] = useState("scenario");
  const [view, setView] = useState<"calculation" | "investigation">("calculation");
  const historyDialog = useRef<HTMLDialogElement>(null);
  const currentInput = { ...input, max_action_cost_gbp: budget === "" ? null : budget.includes(".") ? budget.split(".")[0] + "." + budget.split(".")[1].padEnd(2, "0") : budget + ".00" };
  const selectedSupplier = suppliers.find(s => s.supplier_id === input.supplier_id);
  const supplierOrders = orders.filter(o => o.supplier_id === input.supplier_id);
  const report = run?.report;
  const visibleReport = view === "investigation" ? report : null;
  const assessment = visibleReport?.decision ?? (view === "calculation" ? decision : null);
  const visibleSweep = visibleReport?.counterfactuals ?? (view === "calculation" ? decision?.counterfactuals : null);
  const visibleUncertainty = visibleReport?.uncertainty ?? (view === "calculation" ? decision?.uncertainty : null);
  const recordedInput = view === "investigation" ? run?.request : decisionInput;
  const running = !!run && !terminal.has(run.status);
  const selectedPolicy = assessment?.options.find(o => o.strategy === assessment.recommendation);
  const stale = recordedInput && JSON.stringify(recordedInput) !== JSON.stringify(currentInput);

  function navigate(id: string) {
    setActive(id); if (window.location.hash !== "#" + id) window.history.pushState(null, "", "#" + id);
    document.getElementById(id)?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
  }
  useEffect(() => {
    const controller = new AbortController(); const signal = controller.signal;
    request<Case[]>("/api/v2/cases", { signal }).then(setCases).catch(e => { if (!signal.aborted) setError(String(e)); });
    request<{ suppliers: Supplier[]; orders: Order[] }>("/api/v2/workspace", { signal }, 90_000).then(v => { setSuppliers(v.suppliers); setOrders(v.orders); }).catch(e => { if (!signal.aborted) setError(String(e)); });
    request<Status>("/api/v2/status", { signal }, 90_000).then(setStatus).catch(e => { if (!signal.aborted) setError(String(e)); });
    request<HistoryItem[]>("/api/v2/investigation-runs", { signal }).then(setHistory).catch(e => { if (!signal.aborted) setError("Could not load history: " + String(e)); });
    return () => controller.abort();
  }, [reload]);
  useEffect(() => {
    if (!run || terminal.has(run.status)) return;
    const controller = new AbortController(); let pending = false;
    const timer = window.setInterval(async () => {
      if (pending) return; pending = true;
      try { const next = await request<Run>(`/api/v2/investigation-runs/${run.id}`, { signal: controller.signal }); setRun(next); if (terminal.has(next.status)) request<HistoryItem[]>("/api/v2/investigation-runs").then(setHistory).catch(() => {}); }
      catch (e) { if (!controller.signal.aborted) setError(String(e)); } finally { pending = false; }
    }, 1000);
    return () => { window.clearInterval(timer); controller.abort(); };
  }, [run?.id, run?.status]);
  useEffect(() => { const dialog = historyDialog.current; if (historyOpen && dialog && !dialog.open) dialog.showModal(); if (!historyOpen && dialog?.open) dialog.close(); }, [historyOpen]);
  useEffect(() => {
    const observer = new IntersectionObserver(entries => { const visible = entries.filter(e => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]; if (visible) setActive(visible.target.id); }, { rootMargin: "-120px 0px -45% 0px", threshold: [0, 0.2, 0.5] });
    steps.forEach(s => { const element = document.getElementById(s.id); if (element) observer.observe(element); }); return () => observer.disconnect();
  }, []);
  async function execute(ai: boolean) {
    if (budget !== "" && !/^\d+(?:\.\d{1,2})?$/.test(budget)) { setError("Enter a spending limit of zero or more pounds, with up to two decimal places."); return; }
    if (input.max_late_days !== null && (!Number.isInteger(input.max_late_days) || input.max_late_days < 0 || input.max_late_days > 60)) { setError("Enter a whole-number lateness limit from 0 to 60 days."); return; }
    setError(""); setBusy(ai ? "ai" : "compare"); setHistoryComparison(null);
    try {
      if (ai) { setRun(await request<Run>("/api/v2/investigation-runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(currentInput) })); setView("investigation"); navigate("investigation"); }
      else { const result = await request<Decision>("/api/v2/simulations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(currentInput) }, 90_000); setDecision(result); setDecisionInput(currentInput); setView("calculation"); navigate("results"); }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(null); }
  }
  async function review(action: string) {
    if (!run) return; setReviewBusy(true); setError("");
    try { setRun(await request<Run>(`/api/v2/investigation-runs/${run.id}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, note }) })); setNote(""); }
    catch (e) { setError(String(e)); } finally { setReviewBusy(false); }
  }
  async function loadRun(id: string) { try { setRun(await request<Run>(`/api/v2/investigation-runs/${id}`)); setView("investigation"); setHistoryComparison(null); setHistoryOpen(false); navigate("investigation"); } catch (e) { setError(String(e)); } }
  const services = [{ name: "Zetaris", state: status?.zetaris.status }, { name: "Nightshift", state: status?.nightshift.status }, { name: "H-MEM", state: status?.hmem.status }];
  return <div className="sw-app">
    <a className="sw-skip" href="#scenario">Skip to scenario controls</a>
    <aside className="sw-sidebar">
      <a className="sw-brand" aria-label="Sentry AI" href="#scenario" onClick={e => { e.preventDefault(); navigate("scenario"); }}>Sentry<span>AI</span></a>
      <div className="sw-workspace-label"><span className="sw-workspace-avatar">S</span><div><strong>Operations workspace</strong><small>Supply-chain intelligence</small></div></div>
      <span className="sw-nav-caption">WORKSPACE</span>
      <nav aria-label="Workspace navigation">{steps.map(s => <a key={s.id} href={`#${s.id}`} className={active === s.id ? "is-active" : ""} aria-current={active === s.id ? "location" : undefined} onClick={e => { e.preventDefault(); navigate(s.id); }}><Icon name={s.icon} /><span>{s.name === "Decision" ? "Decision & evidence" : s.name}</span>{active === s.id && <span className="sw-nav-dot" />}</a>)}<button onClick={() => setHistoryOpen(true)}><Icon name="history" /><span>Run history</span><span className="sw-nav-count">{history.length}</span></button></nav>
      <div className="sw-sidebar-bottom"><div className="sw-local-badge"><span className="sw-dot" />LOCAL DEMO WORKSPACE</div><p>Clear evidence.<br /><strong>Confident decisions.</strong></p><span>Synthetic data · Human control</span><a href="/legacy">Open original simulator <Icon name="arrow" size={14} /></a></div>
    </aside>
    <main className="sw-main">
      <header className="sw-topbar"><div className="sw-breadcrumb"><span className="sw-mobile-brand">Sentry AI</span><span className="sw-desktop-crumb">Workspace <Icon name="chevron" size={13} /></span><strong>Disruption intelligence</strong></div><div className="sw-topbar-actions"><span className="sw-demo-pill">Synthetic demo</span><button className="sw-icon-button" aria-label="Open run history" onClick={() => setHistoryOpen(true)}><Icon name="history" /></button><span className="sw-user-avatar" title="Operations workspace">OP</span></div></header>
      <div className="sw-content">
        <div className="sw-page-heading"><div><div className="sw-eyebrow"><span className="sw-dot" />SUPPLY-CHAIN DECISION WORKSPACE</div><h1>When plans change,<br /><span>find your next move.</span></h1><p>Investigate a disruption. Understand your options. Make a decision you can explain.</p></div><div className="sw-heading-note"><div>AI investigates.<br /><strong>You stay in control.</strong></div></div></div>
        <section className="sw-services" aria-label="Integration status"><div className="sw-service-context"><Icon name="database" size={18} /><strong>{status?.data_mode === "zetaris" ? "Live connectors" : status?.data_mode === "fixture" ? "Fixture data" : "Checking sources"}</strong><span className="sw-divider" /><span>25 Oct 2026 evaluation</span></div><div className="sw-service-list">{services.map(s => <span key={s.name} className="sw-service" title={s.state === "reachable" ? "Discovery succeeded; run an investigation to verify inference." : s.state ?? "Checking"}><span className={`sw-service-dot ${s.state === "connected" || s.state === "reachable" ? "is-connected" : s.state === "unavailable" ? "is-unavailable" : ""}`} />{s.name}<small>{s.state ?? "checking"}</small></span>)}<button className="sw-icon-button" aria-label="Refresh connections and history" onClick={() => setReload(v => v + 1)}><Icon name="refresh" size={16} /></button></div></section>
        <nav className="sw-steps" aria-label="Investigation steps">{steps.map((s, i) => <a key={s.id} href={`#${s.id}`} className={active === s.id ? "is-active" : ""} onClick={e => { e.preventDefault(); navigate(s.id); }}><span className="sw-step-number">0{i + 1}</span><span><strong>{s.name}</strong><small>{s.description}</small></span><Icon name="chevron" size={17} /></a>)}</nav>
        {error && <div className="sw-notice is-error" role="alert"><Icon name="info" /><div><strong>Something needs attention</strong><p>{error}</p></div><button className="sw-icon-button" aria-label="Dismiss error" onClick={() => setError("")}><Icon name="close" size={16} /></button></div>}
        <section id="scenario" className="sw-scenario-section"><div className="sw-section-title"><div><span className="sw-section-number">01</span><h2>Set the scenario</h2></div><span className="sw-muted">Start with a case, then make it your own.</span></div>
          <div className="sw-scenario-grid">
            <div className="sw-card sw-scenario-form"><div className="sw-card-heading"><h3>What changed?</h3><span className="sw-tag">What-if simulator</span></div>
              <label className="sw-field">Demonstration case<select aria-label="Demonstration case" value={input.case_id} onChange={e => { const c = cases.find(c => c.case_id === e.target.value); if (c) { setInput({ ...initialInput, supplier_id: c.supplier_id, delay_days: c.delay_days, case_id: c.case_id, max_action_cost_gbp: c.max_action_cost_gbp ?? null, max_late_days: c.max_late_days ?? null }); setBudget(c.max_action_cost_gbp ?? ""); } }}>{!cases.length && <option>Loading cases…</option>}{cases.map(c => <option key={c.case_id} value={c.case_id}>{c.name}</option>)}</select></label>
              <label className="sw-field">Supplier<select aria-label="Supplier" disabled={!suppliers.length} value={input.supplier_id} onChange={e => setInput({ ...input, supplier_id: e.target.value })}>{!suppliers.length && <option>Connecting to source…</option>}{suppliers.map(s => <option key={s.supplier_id} value={s.supplier_id}>{s.name} · {s.supplier_id}</option>)}</select></label>
              <div className="sw-delay-control"><label htmlFor="scenario-delay">Supplier delay</label><output htmlFor="scenario-delay">+{input.delay_days}<span>days</span></output><input id="scenario-delay" aria-label={`Supplier delay: ${input.delay_days} days`} type="range" min="0" max="30" value={input.delay_days} style={{ "--range-progress": `${input.delay_days / 30 * 100}%` } as React.CSSProperties} onChange={e => setInput({ ...input, delay_days: Number(e.target.value) })} /><div className="sw-range-labels"><span>No delay</span><span>30 days</span></div></div>
              <details className="sw-constraints" open={input.case_id === "budget-blocked" || undefined}><summary><span><Icon name="grid" size={16} />Budget & delivery limits <small>Optional</small></span><Icon name="down" size={16} /></summary><div><label className="sw-field">Maximum intervention spending (£, optional)<input type="number" min="0" step="0.01" value={budget} placeholder="No limit" onChange={e => setBudget(e.target.value)} /></label><label className="sw-field">Maximum remaining lateness (days, optional)<input type="number" min="0" max="60" value={input.max_late_days ?? ""} placeholder="No limit" onChange={e => setInput({ ...input, max_late_days: e.target.value === "" ? null : Number(e.target.value) })} /></label><label className="sw-field">Compare against<select aria-label="Compare against" value={input.compare_strategy} onChange={e => setInput({ ...input, compare_strategy: e.target.value as Strategy })}>{Object.entries(strategyLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label></div></details>
              <div className="sw-form-actions"><button className="sw-button is-primary" disabled={!!busy || !suppliers.length || running} onClick={() => execute(true)}><Icon name="spark" size={18} />{busy === "ai" ? "Starting investigation…" : "Run AI investigation"}<Icon name="arrow" size={17} /></button><button className="sw-button is-secondary" disabled={!!busy || !suppliers.length} onClick={() => execute(false)}><Icon name="chart" size={17} />{busy === "compare" ? "Calculating options…" : "Compare calculated options"}</button></div><p className="sw-form-note">AI investigates the evidence. Compare options for a calculation-only preview.</p>
            </div>
            <div className="sw-scenario-overview"><div className="sw-card sw-context-card"><div className="sw-card-heading"><div><span className="sw-kicker">YOUR SCENARIO, AT A GLANCE</span><h3>{selectedSupplier?.name ?? "Connecting your evidence"}</h3></div><span className="sw-context-icon"><Icon name="package" size={25} /></span></div><p className="sw-context-description">{selectedSupplier ? `${selectedSupplier.sku} · ${supplierOrders.length} customer orders in this supplier's dataset` : "Retrieving supplier and order records from the selected data source."}</p>
              <div className="sw-route"><div><span className="sw-route-icon"><Icon name="package" size={23} /></span><strong>Supplier</strong><small>{selectedSupplier?.name ?? "Loading"}</small></div><div className="sw-route-link"><span>+{input.delay_days}d scenario</span><i /></div><div><span className="sw-route-icon is-warehouse"><Icon name="database" size={23} /></span><strong>Stock & recovery</strong><small>Compare three policies</small></div><div className="sw-route-link"><span>Order impact</span><i /></div><div><span className="sw-route-icon"><Icon name="truck" size={23} /></span><strong>Customers</strong><small>{supplierOrders.length} linked orders</small></div></div>
              <div className="sw-context-facts"><div><small>Scheduled restock</small><strong>{selectedSupplier ? shortDate(selectedSupplier.restock_date) : "—"}</strong></div><div><small>Replenishment</small><strong>{selectedSupplier ? `${selectedSupplier.replenishment_quantity} units` : "—"}</strong></div><div><small>Scenario assumption</small><strong>{input.delay_days === 0 ? "No added delay" : `+${input.delay_days} calendar days`}</strong></div></div><p className="sw-footnote"><Icon name="info" size={13} />The delay is your hypothetical input. Source arrival reports are assessed separately.</p></div>
              <div className="sw-explainer"><div><h3>A recommendation with a reason.</h3><p>Sentry gathers evidence, challenges its explanation and verifies the numbers. If the evidence does not hold up, it asks you to resolve the gap.</p><div><span><Icon name="check" size={13} />Evidence linked</span><span><Icon name="check" size={13} />Human decisions</span></div></div></div>
              <details className="sw-connection-details"><summary>Connection details & demonstration limits <Icon name="down" size={14} /></summary><p>All business data is synthetic. Evaluation date: 25 October 2026. Nightshift discovery confirms reachability; only a completed run proves inference. H-MEM guides investigation and never overrides current evidence.</p><pre>{JSON.stringify(status, null, 2)}</pre></details>
            </div>
          </div>
        </section>
        <section id="investigation" className="sw-investigation-section" aria-label="AI investigation"><div className="sw-section-title"><div><span className="sw-section-number">02</span><h2>Follow the investigation</h2></div><button className="sw-text-button" onClick={() => setHistoryOpen(true)}><Icon name="history" size={16} />Previous investigations</button></div>
          <div className="sw-card sw-investigation-card"><div className="sw-card-heading"><div className="sw-investigation-heading"><span className={`sw-round-icon ${running ? "is-running" : ""}`}><Icon name="spark" size={20} /></span><div><h3>{running ? "Working through the evidence" : run ? "Your investigation" : "An answer you can trace"}</h3><p className="sw-muted">Nightshift agents collaborate. Deterministic checks have the final say.</p></div></div>{run && <span className={`sw-tag ${run.status === "validated" ? "is-positive" : running ? "is-working" : "is-warning"}`}>{running && <span className="sw-pulse-dot" />}{run.status === "validated" ? "Validated" : run.status}</span>}</div>
            {!run ? <div className="sw-investigation-empty"><div><h3>Four roles. One accountable decision.</h3><p>Planner → Investigator → Critic → Evaluator</p><span>Choose your scenario above, then run an AI investigation.</span></div><button className="sw-button is-secondary" onClick={() => navigate("scenario")}>Set up scenario<Icon name="arrow" size={16} /></button></div> : <>
              <div className="sw-run-meta"><span role="status" aria-live="polite">Run status: {run.status}</span><code>{run.id}</code><span>{run.request.supplier_id} · +{run.request.delay_days} days</span>{running && <button className="sw-text-button" onClick={async () => { try { setRun(await request<Run>(`/api/v2/investigation-runs/${run.id}/cancel`, { method: "POST" })); } catch (e) { setError(String(e)); } }}>Cancel investigation</button>}</div>
              {run.cancelled && running ? <p role="status" className="sw-muted">Cancellation requested. The active model call may finish before work stops.</p> : null}
              {run.error && <div className="sw-notice is-error" role="alert"><Icon name="info" /><p>{run.error}</p></div>}
              <AgentTimeline run={run} />
              {report && <div className={`sw-agent-conclusion ${report.status !== "validated" ? "is-withheld" : ""}`}><span className="sw-round-icon"><Icon name={report.status === "validated" ? "check" : "info"} /></span><div><span className="sw-kicker">{report.status === "validated" ? "AI recommendation validated" : "Recommendation withheld"}</span><h3>{report.recommended_strategy ? policyName(report.recommended_strategy) : "A human check is needed"}</h3><p>{report.explanation ?? report.validation.unresolved.join("; ")}</p><div className="sw-run-signals"><span>{report.model?.calls ?? 0} model calls</span><span>{report.model?.signed_receipts ?? 0} signed receipts</span><span>{report.memory?.recalled.length ?? 0} memories recalled</span><span>{report.memory?.stored_memory_id ? "Validated finding saved" : "No validated memory saved"}</span></div></div><button className="sw-text-button" onClick={() => { setView("investigation"); navigate("results"); }}>Review decision<Icon name="arrow" size={16} /></button></div>}
              {report && <div className="sw-audit-details"><Disclosure title="Plan, rejected drafts and critiques"><pre>{JSON.stringify({ plan: report.plan, attempts: report.attempts, critiques: report.critiques, validation: report.validation }, null, 2)}</pre></Disclosure><Disclosure title="Source evidence, tools and receipts"><pre>{JSON.stringify({ evidence_ids: report.supporting_evidence_ids, tools: report.tool_calls, model: report.model }, null, 2)}</pre></Disclosure><Disclosure title="Memory, feedback and conflicts"><pre>{JSON.stringify(report.memory, null, 2)}</pre></Disclosure></div>}
              {terminal.has(run.status) && !report && <div className="sw-notice"><Icon name="info" /><p>{run.status === "cancelled" ? "This investigation was cancelled. No recommendation is available." : "No validated report is available. Review the error or try another investigation."}</p></div>}
            </>}
          </div>
        </section>
        <section id="results" className="sw-results-section"><div className="sw-section-title"><div><span className="sw-section-number">03</span><h2>Make an informed decision</h2></div>{assessment && <span className="sw-result-kind">{visibleReport ? "AI investigation result" : "Calculated preview · no AI inference"}</span>}</div>
          {decision && report && <div className="sw-result-switch" aria-label="Result source"><button className={view === "calculation" ? "is-active" : ""} onClick={() => setView("calculation")}>Calculated preview</button><button className={view === "investigation" ? "is-active" : ""} onClick={() => setView("investigation")}>Investigation result</button></div>}
          {stale && <div className="sw-notice is-warning" role="status"><Icon name="info" /><div><strong>Your controls have changed.</strong><p>These results belong to the recorded inputs. Rerun to apply your current scenario.</p></div><button className="sw-text-button" onClick={() => navigate("scenario")}>Back to controls<Icon name="arrow" size={15} /></button></div>}
          {assessment && visibleSweep && visibleUncertainty ? <>
            <div className="sw-result-metrics"><div><span className="sw-metric-icon"><Icon name="activity" /></span><div><small>Penalty exposure</small><strong>{currency(assessment.simulation.estimated_penalty_exposure_gbp)}</strong><span>Before any intervention</span></div></div><div><span className="sw-metric-icon is-green"><Icon name="truck" /></span><div><small>Lowest eligible recovery</small><strong>{currency(selectedPolicy?.total_estimated_cost_gbp)}</strong><span>{selectedPolicy ? policyName(selectedPolicy.strategy) : "No feasible recovery"}</span></div></div><div><span className="sw-metric-icon is-blue"><Icon name="chart" /></span><div><small>Potential cost avoided</small><strong>{currency(selectedPolicy?.saving_vs_no_action_gbp)}</strong><span>Hypothetical, versus no action</span></div></div></div>
            {visibleUncertainty.blocks_recommendation && <div className="sw-notice is-warning"><Icon name="info" /><p>Costs below are calculated scenarios. Conflicting or stale evidence prevents a firm AI recommendation.</p></div>}
            <DecisionView assessment={assessment} sweep={visibleSweep} uncertainty={visibleUncertainty} delay={recordedInput?.delay_days ?? input.delay_days} />
          </> : <div className="sw-card sw-decision-empty"><span className="sw-empty-orbit"><Icon name="chart" size={29} /></span><div><h3>Your decision, backed by the detail.</h3><p>Compare calculated options or finish an AI investigation to see costs, constraints and what would change the recommendation.</p></div><button className="sw-text-button" onClick={() => navigate("scenario")}>Start with a scenario<Icon name="arrow" size={16} /></button></div>}
          {run && terminal.has(run.status) && view === "investigation" && <section className="sw-card sw-human-review" aria-label="Human review"><div className="sw-card-heading"><div><span className="sw-kicker">THE FINAL STEP IS YOURS</span><h2>Review & keep the decision</h2></div><span className={`sw-tag ${run.status === "validated" ? "is-positive" : "is-warning"}`}>{run.status === "validated" ? "Ready for review" : "Approval unavailable"}</span></div><p className="sw-muted">Review applies to {run.id} · {run.request.supplier_id} +{run.request.delay_days} days. It records a decision only; no purchase or shipment is executed.</p>
            <label className="sw-field">Review note<textarea value={note} onChange={e => setNote(e.target.value)} maxLength={1200} placeholder="Add context for your team (optional)…" /></label>
            <div className="sw-review-actions"><div><button className="sw-button is-primary" disabled={run.status !== "validated" || reviewBusy} onClick={() => review("approve")}><Icon name="check" size={17} />Approve recommendation</button><button className="sw-button is-secondary" disabled={reviewBusy} onClick={() => review("request_revision")}>Request revision</button><button className="sw-text-button" disabled={reviewBusy} onClick={() => review("defer")}>Defer decision</button></div><details className="sw-export"><summary><Icon name="download" size={17} />Export packet<Icon name="down" size={14} /></summary><div><a href={`/api/v2/investigation-runs/${run.id}/export?format=markdown`} download>Download Markdown packet</a><a href={`/api/v2/investigation-runs/${run.id}/export?format=json`} download>Download JSON decision packet</a></div></details></div>
            {(run.review ?? []).map((r, i) => <div className="sw-review-record" key={i} role="status"><Icon name="check" size={16} /><p><strong>{r.action === "approve" ? "Recommendation approved" : r.action === "request_revision" ? "Revision requested" : "Decision deferred"}</strong>{r.note && ` · ${r.note}`}<small>{r.effect}</small></p></div>)}
          </section>}
          {historyComparison && <section className="sw-card"><div className="sw-card-heading"><h2>Recorded investigation comparison</h2><button className="sw-icon-button" aria-label="Close comparison" onClick={() => setHistoryComparison(null)}><Icon name="close" size={16} /></button></div><div className="sw-history-comparison">{[historyComparison.previous, historyComparison.current].map((r, i) => <div key={r.run_id}><small>{i === 0 ? "Previous run" : "Current run"} · {r.run_id}</small><h3>{policyName(r.recommendation)}</h3><strong>{currency(r.total_estimated_cost_gbp)}</strong></div>)}</div><p>Cost difference: {currency(historyComparison.cost_difference_gbp)} · {historyComparison.snapshot_changed ? "Different evidence snapshots" : "Same evidence snapshot"}</p><p className="sw-footnote">{historyComparison.limitation}</p></section>}
        </section>
        <footer className="sw-footer"><span><Icon name="shield" size={15} />Synthetic data. Evidence-backed AI. Human decisions.</span><span>Sentry AI · Track 2 <span className="sw-divider" /> <a href="/legacy">Original simulator<Icon name="arrow" size={13} /></a></span></footer>
      </div>
    </main>
    <dialog ref={historyDialog} className="sw-history-dialog" onCancel={() => setHistoryOpen(false)} onClick={e => { if (e.target === e.currentTarget) setHistoryOpen(false); }} aria-labelledby="history-title"><div className="sw-history-content"><div className="sw-card-heading"><div><span className="sw-kicker">YOUR DECISION RECORD</span><h2 id="history-title">Investigation history</h2></div><button className="sw-icon-button" aria-label="Close history" onClick={() => setHistoryOpen(false)}><Icon name="close" /></button></div><p className="sw-muted">Reopen a previous investigation or compare it with your current run.</p><label className="sw-history-search"><Icon name="search" size={18} /><input aria-label="Search investigation history" placeholder="Search by run ID or status…" value={historySearch} onChange={e => setHistorySearch(e.target.value)} /></label><div className="sw-history-list">{history.filter(h => `${h.id} ${h.status}`.toLowerCase().includes(historySearch.toLowerCase())).map(h => <article key={h.id}><span className={`sw-history-status ${h.status === "validated" ? "is-positive" : ""}`}><Icon name={h.status === "validated" ? "check" : "history"} size={19} /></span><div><button onClick={() => loadRun(h.id)}><strong>{h.id}</strong><Icon name="arrow" size={15} /></button><small>{h.created_at ? shortDate(h.created_at) : "Recorded run"} · {h.status}</small>{run && h.id !== run.id && <button className="sw-compare-link" onClick={async () => { try { setHistoryComparison(await request<HistoryComparison>(`/api/v2/investigation-runs/${run.id}/comparison?against=${h.id}`)); setHistoryOpen(false); navigate("results"); } catch (e) { setError(String(e)); } }}>Compare with current run</button>}</div><span className={`sw-tag ${h.status === "validated" ? "is-positive" : ""}`}>{h.status}</span></article>)}</div>{history.length === 0 && <p className="sw-muted">No investigations yet. Your first run will appear here.</p>}{history.length > 0 && !history.some(h => `${h.id} ${h.status}`.toLowerCase().includes(historySearch.toLowerCase())) && <p className="sw-muted" role="status">No investigations match this search.</p>}</div></dialog>
  </div>;
}
