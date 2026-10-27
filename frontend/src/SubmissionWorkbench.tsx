import { useEffect, useRef, useState } from "react";
import { request } from "./api";
import { strategyLabels } from "./format";
import type { Order, Strategy, Supplier } from "./types";
import type { Input, Case, Provenance, Assessment, Sweep, Uncertainty, Decision, Run, Status } from "./workbenchTypes";
import { Icon, DelayChart, AgentTimeline, currency, policyName, shortDate } from "./WorkbenchVisuals";
import "./workbench.css";
import "./guide.css";
import "./review-polish.css";
import { DecisionReasons, PublicDraftFeedback } from "./DecisionReasons";
import { scenarioPresentation } from "./scenarioPresentation";

const terminal = new Set(["validated", "unresolved", "failed", "cancelled"]);
const initialInput: Input = { supplier_id: "SUP-ALPHA", delay_days: 5, case_id: "alpha-delay", max_action_cost_gbp: null, max_late_days: null, compare_strategy: "alternative_supplier" };
type HistoryItem = { id: string; status: string; created_at?: string };
type HistoryComparison = { current: { run_id: string; recommendation: Strategy | null; total_estimated_cost_gbp: string | null }; previous: { run_id: string; recommendation: Strategy | null; total_estimated_cost_gbp: string | null }; cost_difference_gbp: string | null; snapshot_changed: boolean; limitation: string };
const friendlyPolicy = (value: Strategy | null) => value === "expedite_shipping" ? "Speed up the shipment" : value === "alternative_supplier" ? "Use another supplier" : value === "accept_delay" ? "Keep the current plan" : "No option fits your limits";

function Disclosure({ title, children }: { title: string; children: React.ReactNode }) {
  return <details className="sw-disclosure"><summary>{title}<Icon name="down" size={16} /></summary><div className="sw-disclosure-body">{children}</div></details>;
}
function ProvenanceView({ value }: { value: Provenance }) {
  return <Disclosure title={`Data provenance · ${value.data_source}`}><p>Synthetic business records. Snapshot <code>{value.snapshot_hash.slice(0, 16)}</code>.</p><p>Acquired {value.acquired_from} to {value.acquired_until}. Sources were acquired over an interval, not one cross-system transaction.</p><div className="sw-source-queries">{value.queries.map(q => <div key={q.query_id}><Icon name="database" /><div><strong>{q.sources.join(" JOIN ")}</strong><small>{q.rows} rows · query {q.query_id}</small></div></div>)}</div>{!value.queries.length && <p>Explicit fixture data; no live queries were issued.</p>}</Disclosure>;
}
function DecisionView({ assessment, sweep, uncertainty, delay, mode }: { assessment: Assessment; sweep: Sweep; uncertainty: Uncertainty; delay: number; mode: "options" | "change" | "evidence" }) {
  const selected = assessment.options.find(o => o.strategy === assessment.recommendation);
  return <>
    {mode === "options" && <section className="sw-card sw-comparison" aria-label="Decision comparison">
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
    </section>}
    <div className="sw-evidence-grid">
      {mode === "change" && <section className="sw-card" aria-label="Changing decisions"><div className="sw-card-heading"><div><span className="sw-kicker">THE TIPPING POINT</span><h2>What would change the decision?</h2></div><span className="sw-round-icon"><Icon name="chart" /></span></div>
        <p className="sw-change-callout">{sweep.first_change_after_selected_delay ? <>At {sweep.first_change_after_selected_delay.delay_days} days of delay, the preferred policy changes to <strong>{policyName(sweep.first_change_after_selected_delay.strategy)}</strong> ({currency(sweep.first_change_after_selected_delay.cost_gbp)}).</> : "No later decision change was found within the 30-day sweep."}</p>
        <DelayChart key={assessment.provenance.snapshot_hash + delay} sweep={sweep} currentDelay={delay} /><p className="sw-footnote">{sweep.assumption}</p>
        <Disclosure title="Inspect all 31 calculated scenarios"><div className="sw-table-wrap"><table><thead><tr><th>Delay</th><th>Best eligible recovery</th><th>Total</th><th>Selected alternative</th></tr></thead><tbody>{sweep.points.map(p => <tr key={p.delay_days}><td>{p.delay_days} days</td><td>{policyName(p.strategy)}</td><td>{currency(p.cost_gbp)}</td><td>{currency(p.comparison_cost_gbp)} · {p.comparison_eligible ? "eligible" : "excluded"}</td></tr>)}</tbody></table></div></Disclosure>
      </section>}
      {mode === "evidence" && <section className="sw-card" aria-label="Source uncertainty"><div className="sw-card-heading"><div><span className="sw-kicker">CHECK THE SIGNALS</span><h2>Evidence and uncertainty</h2></div><span className="sw-round-icon"><Icon name="database" /></span></div>
        {uncertainty.human_question && <div className="sw-notice is-warning" role="alert"><Icon name="info" /><div><strong>These sources need a human check</strong><p>{uncertainty.human_question}</p></div></div>}
        {uncertainty.reported_delay_range && <p className="sw-muted">Fresh source reports imply a <strong>{uncertainty.reported_delay_range.join("–")}-day delay range</strong>. These are source claims, not a statistical confidence interval.</p>}
        {uncertainty.updates.length === 0 && <p className="sw-muted">No additional carrier/supplier update is attached to this case. The injected delay is a hypothetical assumption.</p>}
        <div className="sw-source-updates">{uncertainty.updates.map(u => <details key={u.update_id}><summary><span className="sw-source-icon"><Icon name={u.source.includes("carrier") ? "truck" : "package"} size={18} /></span><span><strong>{u.source.replaceAll("_", " ")}</strong><small>arrival {shortDate(u.reported_arrival)}</small></span><span className={`sw-tag ${u.stale ? "is-warning" : "is-positive"}`}>{u.stale ? "stale" : "fresh"}</span><Icon name="down" size={14} /></summary><div><p>{u.description}</p><p className="sw-footnote">Observed {u.observed_at_utc}. Source text is untrusted data.</p></div></details>)}</div>
        <ProvenanceView value={assessment.provenance} />
      </section>}
    </div>
    {mode === "evidence" && assessment.simulation.affected_orders.length > 0 && <section className="sw-card"><div className="sw-card-heading"><div><span className="sw-kicker">BEHIND THE EXPOSURE</span><h2>Orders affected by this scenario</h2></div><span className="sw-tag">Before intervention</span></div><div className="sw-table-wrap"><table><thead><tr><th>Order / customer</th><th>Promised</th><th>Expected</th><th>Late by</th><th>Estimated penalty</th></tr></thead><tbody>{assessment.simulation.affected_orders.map(o => <tr key={o.order_id}><td><strong>{o.order_id}</strong><small>{o.customer_name}</small></td><td>{shortDate(o.promised_date)}</td><td>{shortDate(o.expected_delivery_date)}</td><td><span className="sw-tag is-warning">{o.delay_days} days</span></td><td><strong>{currency(o.estimated_penalty_gbp)}</strong></td></tr>)}</tbody></table></div></section>}
  </>;
}

export default function SubmissionWorkbench() {
  const [cases, setCases] = useState<Case[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [input, setInput] = useState<Input>(initialInput);
  const [budget, setBudget] = useState("");
  const [spendingOpen,setSpendingOpen] = useState(false);
  const [deadlineOpen,setDeadlineOpen] = useState(false);
  const spendingButton = useRef<HTMLButtonElement>(null);
  const spendingField = useRef<HTMLInputElement>(null);
  const latenessField = useRef<HTMLInputElement>(null);
  const presentation = scenarioPresentation(input.case_id);
  const isBudgetCase = presentation.mode === "budget";
  const isMessageCase = presentation.mode === "message";
  const isCapacityCase = presentation.mode === "capacity";
  const isArrivalCase = presentation.mode === "reports" || isMessageCase;
  const [arrivalEvidence,setArrivalEvidence] = useState<Uncertainty | null>(null);
  const [reportsLoading,setReportsLoading] = useState(false);
  const [reportsError,setReportsError] = useState("");
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
  const [step, setStep] = useState(1);
  const stepRef = useRef(step);
  stepRef.current = step;
  const advanceRun = useRef<string | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
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
  const answerPresentation = scenarioPresentation(recordedInput?.case_id??input.case_id);
  const runPresentation = scenarioPresentation(run?.request.case_id??input.case_id);
  const running = !!run && !terminal.has(run.status);
  const selectedPolicy = assessment?.options.find(o => o.strategy === assessment.recommendation);
  const stale = recordedInput && JSON.stringify(recordedInput) !== JSON.stringify(currentInput);

  function navigate(id: string) {
    const next = id === "scenario" ? 1 : id === "investigation" ? 2 : 3;
    setStep(next);
    window.history.pushState({guideStep:next}, "", "#" + (next === 1 ? "start" : next === 2 ? "check" : "answer"));
  }
  useEffect(() => { heading.current?.focus({preventScroll:true}); window.scrollTo({top:0,behavior:"instant"}); },[step]);
  useEffect(() => { const back = (e:PopStateEvent) => setStep(e.state?.guideStep ?? 1); window.addEventListener("popstate",back); return () => window.removeEventListener("popstate",back); },[]);
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
      try { const next = await request<Run>(`/api/v2/investigation-runs/${run.id}`, { signal: controller.signal }); setRun(next); if (terminal.has(next.status) && next.report && advanceRun.current === next.id && stepRef.current === 2) { advanceRun.current = null; navigate("results"); } if (terminal.has(next.status)) request<HistoryItem[]>("/api/v2/investigation-runs").then(setHistory).catch(() => {}); }
      catch (e) { if (!controller.signal.aborted) setError(String(e)); } finally { pending = false; }
    }, 1000);
    return () => { window.clearInterval(timer); controller.abort(); };
  }, [run?.id, run?.status]);
  useEffect(() => { const dialog = historyDialog.current; if (historyOpen && dialog && !dialog.open) dialog.showModal(); if (!historyOpen && dialog?.open) dialog.close(); }, [historyOpen]);
  useEffect(() => {
    if (step !== 2 || !isArrivalCase || !suppliers.length) return;
    const controller = new AbortController();
    setReportsLoading(true); setReportsError(""); setArrivalEvidence(null);
    request<Decision>("/api/v2/simulations",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(currentInput),signal:controller.signal},90_000)
      .then(v=>setArrivalEvidence(v.uncertainty))
      .catch(e=>{if(!controller.signal.aborted)setReportsError(String(e));})
      .finally(()=>{if(!controller.signal.aborted)setReportsLoading(false);});
    return ()=>controller.abort();
  },[step,input.case_id,input.supplier_id,suppliers.length]);
  async function execute(ai: boolean) {
    if (!Number.isInteger(input.delay_days) || input.delay_days < 0 || input.delay_days > 30) { setError("Enter a whole-number delivery delay from 0 to 30 days."); return; }
    if (budget !== "" && !/^\d+(?:\.\d{1,2})?$/.test(budget)) { setError("Enter a spending limit of zero or more pounds, with up to two decimal places."); return; }
    if (input.max_late_days !== null && (!Number.isInteger(input.max_late_days) || input.max_late_days < 0 || input.max_late_days > 60)) { setError("Enter a whole-number lateness limit from 0 to 60 days."); return; }
    setError(""); setBusy(ai ? "ai" : "compare"); setHistoryComparison(null);
    try {
      if (ai) { const next = await request<Run>("/api/v2/investigation-runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(currentInput) }); advanceRun.current = next.id; setRun(next); setView("investigation"); if (next.report && terminal.has(next.status)) navigate("results"); }
      else { const result = await request<Decision>("/api/v2/simulations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(currentInput) }, 90_000); setDecision(result); setDecisionInput(currentInput); setView("calculation"); navigate("results"); }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(null); }
  }
  async function review(action: string) {
    if (!run) return; setReviewBusy(true); setError("");
    try { setRun(await request<Run>(`/api/v2/investigation-runs/${run.id}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, note }) })); setNote(""); }
    catch (e) { setError(String(e)); } finally { setReviewBusy(false); }
  }
  async function loadRun(id: string) { try { setRun(await request<Run>(`/api/v2/investigation-runs/${id}`)); setView("investigation"); setHistoryComparison(null); setHistoryOpen(false); advanceRun.current = null; navigate("results"); } catch (e) { setError(String(e)); } }
  function chooseCase(id:string) {
    if (running) return;
    const c=cases.find(c=>c.case_id===id); if (!c) return;
    setRun(null); setDecision(null); setDecisionInput(null); setView("calculation"); setHistoryComparison(null); advanceRun.current=null;
    setInput({...initialInput,supplier_id:c.supplier_id,delay_days:c.delay_days,case_id:c.case_id,max_action_cost_gbp:c.max_action_cost_gbp??null,max_late_days:c.max_late_days??null});
    setBudget(c.max_action_cost_gbp??""); setSpendingOpen(false); setDeadlineOpen(false); setError("");
  }
  const blocked=!!visibleUncertainty?.blocks_recommendation;
  const accepted=view==="investigation" && report?.status==="validated";
  const hasAnswer=!!assessment && !!visibleSweep && !!visibleUncertainty;
  const chosenSituation = presentation.label;
  const answerHeading = blocked?"One detail needs checking.":hasAnswer&&!assessment?.recommendation?"Your limits need a rethink.":!hasAnswer?"This check has no answer yet.":view==="investigation"&&report?.status!=="validated"?"We couldn't confirm a safe answer.":answerPresentation.mode==="message"?(view==="calculation"?"Costs are ready. The message isn't checked.":"Here's the evidence-backed plan."):answerPresentation.mode==="capacity"?"Here's what the backup can cover.":answerPresentation.mode==="on-time"&&assessment?.simulation.estimated_penalty_exposure_gbp==="0.00"?"No extra action is needed.":recordedInput?.case_id==="long-delay"?"Here's a plan for the long delay.":"Here's your next move.";

  const delayControl = <div className="gu-delay"><output>{input.delay_days}<span>{presentation.mode==="on-time"?"extra days":input.delay_days===1?"day late":"days late"}</span></output><div className="gu-delay-slider"><button aria-label="Reduce delay by one day" disabled={input.delay_days===0} onClick={()=>setInput({...input,delay_days:input.delay_days-1})}>−</button><input type="range" min="0" max="30" aria-label="Delivery delay" style={{"--delay-fill":`${input.delay_days/30*100}%`} as React.CSSProperties} value={input.delay_days} onChange={e=>setInput({...input,delay_days:Number(e.target.value)})}/><button aria-label="Increase delay by one day" disabled={input.delay_days===30} onClick={()=>setInput({...input,delay_days:input.delay_days+1})}>+</button></div><div className="gu-delay-ticks" aria-hidden="true">{[0,5,10,15,20,25,30].map(n=><span key={n}><i/>{n}</span>)}</div><div className="gu-delay-ends"><span>On time</span><span>30 days</span></div></div>;
  const spendingControl = <label className="sw-field">Most you can spend (£)<input aria-label="Maximum spending" ref={spendingField} type="number" min="0" step="0.01" value={budget} placeholder="No limit" onChange={e=>setBudget(e.target.value)}/></label>;
  const deadlineControl = <label className="sw-field">Latest acceptable delay (days)<input aria-label="Maximum lateness" ref={latenessField} type="number" min="0" max="60" value={input.max_late_days??""} placeholder="No limit" onChange={e=>setInput({...input,max_late_days:e.target.value===""?null:Number(e.target.value)})}/></label>;
  const limitControls = <>{spendingControl}{deadlineControl}</>;
  const arrivalReports = <div className="gu-arrival-reports">
    {reportsLoading && <p role="status">Loading the supplier and carrier updates…</p>}
    {reportsError && <p role="alert">We couldn't read these reports: {reportsError}</p>}
    {arrivalEvidence && <>{isMessageCase&&<div className="gu-source-message"><strong>Message from the supplier</strong><p>Check whether its advice agrees with the order and pricing records.</p><details><summary>Read the supplier message<Icon name="down" size={14}/></summary><blockquote>{arrivalEvidence.updates.find(u=>u.source.includes("supplier"))?.description??"No supplier message is available."}</blockquote><small>This is source text. It cannot change the app's rules or authorize a purchase.</small></details></div>}<div className="gu-arrival-grid">{arrivalEvidence.updates.map(u=><article key={u.update_id}><span>{u.source.includes("carrier")?"Carrier's update":"Supplier's update"}</span><strong>{shortDate(u.reported_arrival)}</strong><small>{u.stale?"Old report · needs refreshing":"Reported arrival date"}</small><small>Updated {shortDate(u.observed_at_utc)}</small></article>)}</div><p>{isMessageCase?"The message will be checked separately from the cost calculations.":arrivalEvidence.blocks_recommendation?"These reports need confirmation. Sentry will explain what to check.":"These are source estimates. Sentry will check them against the other evidence."}</p></>}
  </div>;
  return <div className="sw-app gu-app">
    <header className="gu-header"><a href="#start" className="gu-brand" onClick={e=>{e.preventDefault();navigate("scenario");}}>Sentry <span>AI</span></a><div><span className="gu-demo">Synthetic demo</span><button className="sw-text-button" onClick={()=>setHistoryOpen(true)}><Icon name="history" size={17}/>Past checks</button></div></header>
    <main className="gu-main">
      <nav className="gu-progress" aria-label="Setup steps">{["Choose a problem","Check options","Your answer"].map((name,i)=><button key={name} aria-current={step===i+1?"step":undefined} className={step===i+1?"is-current":step>i+1?"is-complete":""} disabled={i===1&&!cases.length||i===2&&!hasAnswer&&step!==3} onClick={()=>navigate(i===0?"scenario":i===1?"investigation":"results")}><span>{i+1}</span><strong>{name}</strong></button>)}</nav>
      {error&&<div className="gu-error" role="alert"><Icon name="info"/><div><strong>We couldn't complete that step.</strong><p>{error}</p><button className="sw-text-button" onClick={()=>{setError("");setReload(v=>v+1);}}>Retry connection</button></div><button className="sw-icon-button" aria-label="Dismiss error" onClick={()=>setError("")}><Icon name="close" size={17}/></button></div>}
      {step===1&&<section className="gu-screen" aria-labelledby="guide-title">
        <div className="gu-intro"><span>STEP 1 OF 3</span><h1 id="guide-title" tabIndex={-1} ref={heading}>What do you need help with?</h1><p>Choose a situation. We'll guide you through the rest.</p></div>
        <div className="gu-choices">{[{id:"alpha-delay",icon:"truck",title:"A delivery is late",text:"Find the best way to keep orders moving."},{id:"budget-blocked",icon:"chart",title:"Recovery costs too much",text:"See what works within your budget."},{id:"conflicting-eta",icon:"info",title:"Arrival reports disagree",text:"Find out what needs checking."}].map(c=><button key={c.id} className={`${c.id==="alpha-delay"?"case-delay":c.id==="budget-blocked"?"case-budget":"case-reports"} ${input.case_id===c.id?"is-selected":""}`} aria-pressed={input.case_id===c.id} disabled={!cases.length||running} onClick={()=>chooseCase(c.id)}><span className="gu-choice-icon"><Icon name={c.icon} size={24}/></span><span><strong>{c.title}</strong><small>{c.text}</small></span><span className="gu-choice-radio">{input.case_id===c.id&&<span/>}</span></button>)}</div>
        <details className="gu-more gu-more-examples"><summary>More examples<Icon name="down" size={18}/></summary><label className="sw-field">Example situation<select aria-label="Example situation" disabled={running} value={input.case_id} onChange={e=>chooseCase(e.target.value)}>{(["Delivery plans","Check information"] as const).map(group=><optgroup key={group} label={group}>{cases.filter(c=>scenarioPresentation(c.case_id,c.name).group===group).map(c=><option key={c.case_id} value={c.case_id}>{scenarioPresentation(c.case_id,c.name).label}</option>)}</optgroup>)}</select></label></details>
        {!["alpha-delay","budget-blocked","conflicting-eta"].includes(input.case_id)&&<p className="gu-selected-example" role="status">Selected example: <strong>{presentation.label}</strong></p>}
        <div className="gu-next"><button className="sw-button is-primary" disabled={!cases.length} onClick={()=>navigate("investigation")}>Continue<Icon name="arrow" size={18}/></button><span>You can change the details next.</span></div>
      </section>}
      {step===2&&<section className="gu-screen" aria-label="AI investigation" aria-labelledby="guide-title">
        <div className="gu-intro"><span>STEP 2 OF 3</span><h1 id="guide-title" tabIndex={-1} ref={heading}>{running?"We're checking your options.":presentation.heading}</h1><p>{running?"You can stay here. Your answer will appear when the checks finish.":presentation.intro}</p></div>
        {running?<div className="sw-card gu-checking"><div className="gu-working-orbit"><Icon name="spark" size={32}/></div><h2>{runPresentation.working}</h2><p role="status" aria-live="polite">{run?.events.at(-1)?.agent==="critic"?"Checking the explanation against the facts…":run?.events.at(-1)?.agent==="memory"?"Checking relevant past findings…":run?.events.at(-1)?.agent==="feedback"?"Checking a gap before giving you an answer…":"Reading the evidence and comparing costs…"}</p><span className="gu-working-state">{run?.status==="queued"?"Waiting to start":"AI check in progress"}</span><details className="gu-details"><summary>See what's happening<Icon name="down" size={15}/></summary>{run&&<AgentTimeline run={run}/>}</details><button className="sw-text-button" onClick={async()=>{if(!run)return;advanceRun.current=null;try{setRun(await request<Run>(`/api/v2/investigation-runs/${run.id}/cancel`,{method:"POST"}));}catch(e){setError(String(e));}}}>Cancel check</button></div>:<>
          <div className="sw-card gu-setup"><div className="gu-supplier"><span className="gu-choice-icon"><Icon name="truck" size={23}/></span><div><strong>{selectedSupplier?.name??"Connecting to data…"}</strong><small>{chosenSituation}{suppliers.length?` · ${supplierOrders.length} linked orders`:""}</small></div><button className="sw-text-button" onClick={()=>navigate("scenario")}>Change</button></div>
            {supplierOrders.length>0&&<details className="gu-order-peek"><summary>{supplierOrders.length} customer orders will be checked<Icon name="down" size={14}/></summary><ul>{supplierOrders.map(o=><li key={o.order_id}><span><strong>{o.customer_name}</strong><small>{o.order_id} · {o.quantity} units</small></span><span>Due {shortDate(o.promised_date)}</span></li>)}</ul></details>}
            {isBudgetCase?<div className="gu-budget-inputs">{limitControls}<p className="gu-context-line">This example has a delivery delayed by {input.delay_days} days.</p></div>:isArrivalCase?arrivalReports:isCapacityCase?<div className="gu-capacity"><div className="gu-capacity-grid"><article><span>Expedited stock offer</span><strong>{selectedSupplier?.expedite.capacity_units??"—"} units</strong></article><article><span>Another supplier's offer</span><strong>{selectedSupplier?.alternative.capacity_units??"—"} units</strong></article></div><p>This example is {input.delay_days} days late. Sentry checks which orders the recorded backup offers can cover.</p></div>:delayControl}
            {!isBudgetCase&&<section className="gu-limit-options" aria-label="Optional limits"><div className="gu-limit-heading"><strong>Want to set limits?</strong><span>Optional</span></div><div className="gu-limit-tiles"><button ref={spendingButton} aria-expanded={spendingOpen} aria-controls="spending-fields" onClick={()=>{setSpendingOpen(v=>!v);if(!spendingOpen)requestAnimationFrame(()=>spendingField.current?.focus());}}><Icon name="chart" size={18}/><span><strong>Spending limit</strong><small>{budget!==""&&/^\d+(?:\.\d{0,2})?$/.test(budget)?`${currency(budget)} maximum`:"Keep within your budget"}</small></span><Icon name="chevron" size={15}/></button><button aria-expanded={deadlineOpen} aria-controls="deadline-fields" onClick={()=>{setDeadlineOpen(v=>!v);if(!deadlineOpen)requestAnimationFrame(()=>latenessField.current?.focus());}}><Icon name="history" size={18}/><span><strong>Delivery deadline</strong><small>{input.max_late_days===null?"Set the latest acceptable delay":`${input.max_late_days} late days maximum`}</small></span><Icon name="chevron" size={15}/></button></div>{spendingOpen&&<div id="spending-fields" className="gu-limit-fields">{spendingControl}</div>}{deadlineOpen&&<div id="deadline-fields" className="gu-limit-fields">{deadlineControl}</div>}{(spendingOpen||deadlineOpen)&&<button className="sw-text-button gu-done-limits" onClick={()=>{setSpendingOpen(false);setDeadlineOpen(false);spendingButton.current?.focus();}}>Done setting limits<Icon name="check" size={15}/></button>}</section>}

            <details className="gu-more gu-edit-scenario"><summary><span className="gu-edit-icon"><Icon name="grid" size={19}/></span><span><strong>Change supplier or comparison</strong><small>{isBudgetCase||isArrivalCase||isCapacityCase?"Adjust the supplier, delay or recovery option.":"Pick another supplier or recovery option."}</small></span><Icon name="down" size={17}/></summary><div className="gu-edit-fields">{(isBudgetCase||isArrivalCase||isCapacityCase)&&<label className="sw-field">Delay to test (days)<input aria-label="Delivery delay to test" type="number" min="0" max="30" value={input.delay_days} onChange={e=>setInput({...input,delay_days:Number(e.target.value)})}/></label>}<label className="sw-field">Supplier<select aria-label="Supplier" disabled={!suppliers.length} value={input.supplier_id} onChange={e=>setInput({...input,supplier_id:e.target.value})}>{!suppliers.length&&<option>Connecting…</option>}{suppliers.map(s=><option key={s.supplier_id} value={s.supplier_id}>{s.name}</option>)}</select></label><label className="sw-field">Compare with<select aria-label="Compare against" value={input.compare_strategy} onChange={e=>setInput({...input,compare_strategy:e.target.value as Strategy})}>{Object.entries(strategyLabels).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><button className="sw-text-button" onClick={e=>{const panel=e.currentTarget.closest("details");if(panel){panel.open=false;panel.querySelector("summary")?.focus();}}}>Done editing<Icon name="check" size={15}/></button></div></details>
            {run?.status==="cancelled"&&<p className="gu-inline-message" role="status">Check cancelled. You can change the details and try again.</p>}{run?.error&&<p className="gu-inline-message" role="alert">The check stopped: {run.error}</p>}
            <button className="sw-button is-primary gu-primary" disabled={!!busy||!suppliers.length} onClick={()=>execute(true)}><Icon name="spark" size={19}/>{busy==="ai"?"Starting…":presentation.action}<Icon name="arrow" size={18}/></button><p className="gu-action-note">{isMessageCase?"Uses AI to check the message against the source evidence.":isArrivalCase?"Uses AI to check whether the source updates can be trusted.":"Uses AI to check the evidence and compare costs."}</p>
          </div><div className="gu-under-actions"><button className="sw-text-button" onClick={()=>navigate("scenario")}><Icon name="chevron" size={14}/>Back</button><button className="sw-text-button" disabled={!!busy||!suppliers.length} onClick={()=>execute(false)}>{busy==="compare"?"Checking…":presentation.preview}</button></div>
        </>}
      </section>}
      {step===3&&<section className="gu-screen" aria-labelledby="guide-title">
        <div className="gu-intro"><span>STEP 3 OF 3</span><h1 id="guide-title" tabIndex={-1} ref={heading}>{answerHeading}</h1><p>{recordedInput?`${suppliers.find(s=>s.supplier_id===recordedInput.supplier_id)?.name??recordedInput.supplier_id} · ${answerPresentation.mode==="delay"?`${recordedInput.delay_days} days late`:answerPresentation.context}`:"Start a new check to compare your options."}</p></div>
        {stale&&<div className="gu-inline-message" role="status">These results use your earlier details. <button className="sw-text-button" onClick={()=>navigate("investigation")}>Change details and check again</button></div>}
        {hasAnswer&&assessment&&visibleSweep&&visibleUncertainty?<>
          <article className={`sw-card gu-answer ${blocked||!assessment.recommendation||view==="investigation"&&!accepted?"needs-review":""}`} aria-label="Your answer">
            <span className="gu-answer-status">{blocked?"Waiting for a human check":view==="calculation"?"Cost preview · AI was not used":accepted?"AI checked · Figures verified":"AI could not confirm an answer"}</span>
            <h2>{blocked?(recordedInput?.case_id==="stale-update"?"Get a fresh arrival update first":"Confirm the arrival date first"):!assessment.recommendation?"No option fits your budget and deadline":view==="investigation"&&!accepted?"We couldn't confirm a recommendation":answerPresentation.mode==="message"&&view==="calculation"?"Cost preview — message not yet reviewed":friendlyPolicy(assessment.recommendation)}</h2>
            {blocked?<p>{visibleUncertainty.human_question}</p>:!assessment.recommendation?<p>Try increasing your spending limit or allowing a little more time. No recommendation has been approved.</p>:view==="investigation"&&!accepted?<p>{report?.validation.unresolved.join("; ")||"Review the evidence or try again."}</p>:<><div className="gu-answer-cost"><strong>{currency(selectedPolicy?.total_estimated_cost_gbp)}</strong><span>total estimated cost</span></div><p>{selectedPolicy?.strategy==="accept_delay"&&assessment.simulation.estimated_penalty_exposure_gbp==="0.00"?"The orders can stay on track without spending more.":`This is the cheapest option that meets your limits. Doing nothing would cost ${currency(assessment.simulation.estimated_penalty_exposure_gbp)}.`}</p>{selectedPolicy&&<div className="gu-answer-facts"><span><strong>{currency(selectedPolicy.saving_vs_no_action_gbp)}</strong> less than doing nothing</span><span><strong>{selectedPolicy.max_remaining_late_days} {selectedPolicy.max_remaining_late_days===1?"day":"days"}</strong> remaining delay</span></div>}</>}
            {!blocked&&selectedPolicy&&(view==="calculation"||accepted)&&<DecisionReasons assessment={assessment}/>}
            {accepted&&!blocked&&<div className="gu-approve"><button className="sw-button is-primary" disabled={reviewBusy||!!run?.review?.some(r=>r.action==="approve")} onClick={()=>review("approve")}><Icon name="check" size={18}/>{run?.review?.some(r=>r.action==="approve")?"Plan approved":"Approve this plan"}</button><span>Approval records your choice. It doesn't place an order.</span></div>}
            {run?.review?.length? <p className="gu-inline-message" role="status">{run.review.at(-1)?.action==="approve"?"Your approval is saved.":run.review.at(-1)?.action==="defer"?"Decision deferred.":"Revision requested."}</p>:null}
            {answerPresentation.mode==="message"&&<p className="gu-case-outcome">{view==="calculation"?"This preview compares costs only. The supplier message has not been reviewed by AI.":accepted?"The recommendation passed checks against source evidence; the message could not override the calculated figures.":"The message check could not produce a validated recommendation."}</p>}
            {answerPresentation.mode==="capacity"&&selectedPolicy&&<p className="gu-case-outcome">{selectedPolicy.max_remaining_late_days>0?`Backup capacity is limited. This option still leaves up to ${selectedPolicy.max_remaining_late_days} ${selectedPolicy.max_remaining_late_days===1?"day":"days"} of lateness.`:"This option covers the deadlines within the recorded capacity limits."}</p>}
            <p className="gu-hypothetical">Synthetic example. Costs are estimates, not realized savings.</p>
          </article>
          <div className="gu-answer-actions"><button className="sw-text-button" onClick={()=>navigate("investigation")}><Icon name="refresh" size={15}/>Change the details</button>{run&&view==="investigation"&&terminal.has(run.status)&&<a className="sw-text-button" href={`/api/v2/investigation-runs/${run.id}/export?format=markdown`} download><Icon name="download" size={16}/>Download report</a>}</div>
          <div className="gu-result-details">
            <details className="gu-details"><summary>Compare the three options<Icon name="down" size={17}/></summary><DecisionView mode="options" assessment={assessment} sweep={visibleSweep} uncertainty={visibleUncertainty} delay={recordedInput?.delay_days??input.delay_days}/></details>
            <details className="gu-details"><summary>What if the delay changes?<Icon name="down" size={17}/></summary><DecisionView mode="change" assessment={assessment} sweep={visibleSweep} uncertainty={visibleUncertainty} delay={recordedInput?.delay_days??input.delay_days}/></details>
            <details className="gu-details"><summary>See how we reached this<Icon name="down" size={17}/></summary>
              {visibleReport&&<><Disclosure title="Read the AI explanation"><p>{visibleReport.explanation??visibleReport.validation.unresolved.join("; ")}</p></Disclosure>{run&&<AgentTimeline run={run}/>}<Disclosure title="Agent plan and checks"><ol className="gu-readable-plan">{visibleReport.plan.map(p=><li key={p.task_id}>{p.question}<small>{p.origin==="planner"?"Agent-selected question":p.origin==="memory"?"Prompted by a past finding":"Required evidence check"}</small></li>)}</ol><PublicDraftFeedback attempts={visibleReport.attempts}/><ul className="gu-check-list">{visibleReport.validation.checks?.map(c=><li key={c.check}><Icon name={c.passed?"check":"info"} size={15}/><span>{c.check.replaceAll("_"," ")}<small>{c.detail}</small></span></li>)}</ul></Disclosure><Disclosure title="AI calls and memory"><div className="gu-readable-metadata"><p><strong>{visibleReport.model?.calls??0} AI calls</strong> through Nightshift.</p><p>Model used: {visibleReport.model?.models_used.join(", ")||"No model was needed"}.</p><p>{visibleReport.model?.signed_receipts??0} receipt envelopes returned. Signatures are not independently verified.</p><p><strong>{visibleReport.memory?.recalled.length??0} past findings recalled</strong>. {visibleReport.memory?.stored_memory_id?"This validated finding was saved.":"No new validated finding was saved."}</p><p>Current costs were recalculated before using past findings.</p></div></Disclosure></>}
              <DecisionView mode="evidence" assessment={assessment} sweep={visibleSweep} uncertainty={visibleUncertainty} delay={recordedInput?.delay_days??input.delay_days}/>
              {run&&view==="investigation"&&<a className="sw-text-button" href={`/api/v2/investigation-runs/${run.id}/export?format=json`} download>Download full JSON record</a>}
            </details>
            {run&&view==="investigation"&&terminal.has(run.status)&&<details className="gu-details"><summary>Leave a note or postpone<Icon name="down" size={17}/></summary><label className="sw-field">Your note<textarea value={note} maxLength={1200} onChange={e=>setNote(e.target.value)} placeholder="What needs to change?"/></label><div className="gu-note-actions"><button className="sw-button is-secondary" disabled={reviewBusy} onClick={()=>review("request_revision")}>Request a revision</button><button className="sw-text-button" disabled={reviewBusy} onClick={()=>review("defer")}>Decide later</button></div></details>}
          </div>
        </>:<div className="sw-card gu-answer"><h2>{run?.status==="cancelled"?"This check was cancelled":"No completed report is available"}</h2><p>{run?.error??"Change the details or start a new check."}</p><button className="sw-button is-primary" onClick={()=>navigate("investigation")}>Try again<Icon name="arrow" size={17}/></button></div>}
        {historyComparison&&<details className="gu-details" open><summary>Previous check comparison<Icon name="down" size={17}/></summary><div className="sw-history-comparison">{[historyComparison.previous,historyComparison.current].map((r,i)=><div key={i}><small>{i===0?"Previous":"Current"}</small><h3>{friendlyPolicy(r.recommendation)}</h3><strong>{currency(r.total_estimated_cost_gbp)}</strong></div>)}</div><p className="sw-muted">{historyComparison.limitation}</p></details>}
        <div className="gu-new-check"><button className="sw-text-button" onClick={()=>{advanceRun.current=null;navigate("scenario");}}>Start another check<Icon name="arrow" size={16}/></button></div>
      </section>}
      <footer className="gu-footer"><span>Demo with synthetic data · You make the final decision.</span><details><summary>Data & connections<Icon name="down" size={13}/></summary><div className="gu-connection-card"><h3>Connected services</h3><ul><li><Icon name="database"/><span><strong>Zetaris data</strong><small>{status?.data_mode==="fixture"?"Using the labelled sample files":status?.zetaris.status==="connected"?"Source data connected":status?.zetaris.status==="unavailable"?"Data connection needs attention":"Checking the data connection"}</small></span></li><li><Icon name="spark"/><span><strong>Nightshift AI</strong><small>{status?.nightshift.status==="reachable"?"Runtime reachable; each completed report records actual AI usage":status?.nightshift.status==="unavailable"?"AI runtime needs attention":"Checking the AI runtime"}</small></span></li><li><Icon name="history"/><span><strong>H-MEM memory</strong><small>{status?.hmem.status==="connected"?"Memory engine connected":status?.hmem.status==="unavailable"?"Memory needs attention":"Checking memory"}</small></span></li></ul><p>Synthetic records, evaluated as of 25 October 2026. Technical receipts and source references are available with each answer.</p><button className="sw-text-button" onClick={()=>setReload(v=>v+1)}>Refresh status<Icon name="refresh" size={14}/></button></div></details></footer>
    </main>
    <dialog ref={historyDialog} className="sw-history-dialog gu-history" onCancel={()=>setHistoryOpen(false)} onClick={e=>{if(e.target===e.currentTarget)setHistoryOpen(false);}} aria-labelledby="history-title"><div className="sw-history-content"><div className="sw-card-heading"><h2 id="history-title">Past checks</h2><button className="sw-icon-button" aria-label="Close past checks" onClick={()=>setHistoryOpen(false)}><Icon name="close"/></button></div><label className="sw-history-search"><Icon name="search" size={18}/><input aria-label="Search past checks" placeholder="Search by date, status or ID" value={historySearch} onChange={e=>setHistorySearch(e.target.value)}/></label><div className="sw-history-list">{history.filter(h=>`${h.id} ${h.status} ${h.created_at??""}`.toLowerCase().includes(historySearch.toLowerCase())).map(h=><article key={h.id}><div><button onClick={()=>loadRun(h.id)}><strong>{h.created_at?new Date(h.created_at).toLocaleString("en-GB",{day:"numeric",month:"short",hour:"2-digit",minute:"2-digit"}):h.id}</strong><Icon name="arrow" size={16}/></button><small>{h.status} · {h.id}</small>{run&&h.id!==run.id&&<button className="sw-compare-link" onClick={async()=>{try{setHistoryComparison(await request<HistoryComparison>(`/api/v2/investigation-runs/${run.id}/comparison?against=${h.id}`));setHistoryOpen(false);navigate("results");}catch(e){setError(String(e));}}}>Compare with current check</button>}</div><span className={`sw-tag ${h.status==="validated"?"is-positive":""}`}>{h.status==="validated"?"Checked":h.status}</span></article>)}</div>{!history.length&&<p className="sw-muted">Your completed checks will appear here.</p>}</div></dialog>
  </div>;
}
