import { useEffect, useState } from "react";
import { request } from "./api";
import { strategyLabels } from "./format";
import type { Simulation, Strategy, Supplier } from "./types";

type Input = { supplier_id: string; delay_days: number; case_id: string; max_action_cost_gbp: string | null; max_late_days: number | null; compare_strategy: Strategy };
type Case = { case_id: string; name: string; supplier_id: string; delay_days: number; max_action_cost_gbp?: string; max_late_days?: number };
type Provenance = { snapshot_hash: string; data_source: string; synthetic: boolean; acquired_from: string; acquired_until: string; queries: { query_id: string; sources: string[]; rows: number }[] };
type Option = Simulation["recovery_options"][number] & { eligible: boolean; max_remaining_late_days: number; exclusion_reasons: string[] };
type Point = { delay_days: number; strategy: Strategy | null; cost_gbp: string | null; comparison_cost_gbp: string; comparison_eligible: boolean };
type Assessment = { simulation: Simulation; options: Option[]; recommendation: Strategy | null; feasibility: string; provenance: Provenance };
type Sweep = { points: Point[]; first_change_after_selected_delay: Point | null; assumption: string; arrival_range_outcomes: Point[] };
type Uncertainty = { updates: { update_id: string; source: string; reported_arrival: string; observed_at_utc: string; stale: boolean; description: string }[]; blocks_recommendation: boolean; human_question: string | null; reported_delay_range: number[] | null };
type Decision = Assessment & { counterfactuals: Sweep; uncertainty: Uncertainty };
type Report = { status: string; recommended_strategy: Strategy | null; explanation: string | null; decision: Assessment; counterfactuals: Sweep; uncertainty: Uncertainty; provenance: Provenance; validation: { passed: boolean; unresolved: string[]; checks?: { check: string; passed: boolean; detail: string }[] }; supporting_evidence_ids: string[]; plan: { task_id: string; question: string; tool: string; origin: string }[]; tool_calls: { call_id: string; tool: string; status: string; summary: string; result: unknown }[]; attempts: unknown[]; critiques: unknown[]; model: { models_used: string[]; calls: number; signed_receipts: number; receipt_ids: string[] } | null; memory: { recalled: { memory_id: string; content: string; use: string }[]; stored_memory_id: string | null; feedback: unknown[]; conflicts: unknown[] } | null; disclaimer: string };
type Run = { id: string; status: string; request: Input; events: { at: string; agent: string; message: string }[]; report: Report | null; error: string | null; cancelled: number; review: { action: string; note: string; effect: string }[] | null };
type Status = { data_mode: string; zetaris: { status: string; reason?: string }; nightshift: { status: string; requested_model?: string; reason?: string }; hmem: { status: string; reason?: string } };
const terminal = new Set(["validated", "unresolved", "failed", "cancelled"]);
const label = (value: Strategy | null) => value ? strategyLabels[value] : "No feasible recovery";
const money = (value: string | null) => value === null ? "—" : new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(Number(value));

function ProvenanceView({ value }: { value: Provenance }) {
  return <details><summary>Data provenance · {value.data_source}</summary><p>Synthetic business records. Snapshot <code>{value.snapshot_hash.slice(0,16)}</code>.</p><p>Acquired {value.acquired_from} to {value.acquired_until}. Sources are queried over an interval, not one cross-system transaction.</p><ul>{value.queries.map(q => <li key={q.query_id}>{q.sources.join(" JOIN ")} · {q.rows} rows · query <code>{q.query_id}</code></li>)}</ul></details>;
}

function DecisionView({ assessment, sweep, uncertainty }: { assessment: Assessment; sweep: Sweep; uncertainty: Uncertainty }) {
  return <>
    <section className="agent-panel" aria-label="Decision comparison">
      <h2>Why this option, why not the others?</h2>
      <p>Calculated penalty exposure: <strong>{money(assessment.simulation.estimated_penalty_exposure_gbp)}</strong>. {uncertainty.blocks_recommendation ? "A firm recommendation is withheld pending evidence review." : `Lowest-cost eligible policy: ${label(assessment.recommendation)}.`}</p>
      <div className="table-scroll"><table><thead><tr><th>Recovery</th><th>Action</th><th>Residual penalties</th><th>Total</th><th>Worst lateness</th><th>Eligibility</th></tr></thead><tbody>{assessment.options.map(o => <tr key={o.strategy}><td>{label(o.strategy)}</td><td>{money(o.action_cost_gbp)}</td><td>{money(o.residual_penalty_gbp)}</td><td>{money(o.total_estimated_cost_gbp)}</td><td>{o.max_remaining_late_days} days</td><td>{o.eligible ? "Eligible" : o.exclusion_reasons.join("; ")}</td></tr>)}</tbody></table></div>
      {assessment.recommendation === null && <p role="status"><strong>No feasible recovery under these constraints.</strong></p>}
      <details><summary>Capacity, arrival and fee assumptions</summary>{assessment.options.map(o => <p key={o.strategy}><strong>{label(o.strategy)}:</strong> {o.details}</p>)}</details>
    </section>
    <section className="agent-panel" aria-label="Changing decisions"><h2>What would change the decision?</h2><p>{sweep.first_change_after_selected_delay ? `At ${sweep.first_change_after_selected_delay.delay_days} days of delay, the preferred policy changes to ${label(sweep.first_change_after_selected_delay.strategy)} (${money(sweep.first_change_after_selected_delay.cost_gbp)}).` : "No later decision change was found within the 30-day sweep."}</p><p>{sweep.assumption}</p><details><summary>Inspect all 31 calculated scenarios</summary><div className="table-scroll"><table><thead><tr><th>Delay</th><th>Best eligible recovery</th><th>Total</th><th>Selected alternative</th></tr></thead><tbody>{sweep.points.map(p => <tr key={p.delay_days}><td>{p.delay_days} days</td><td>{label(p.strategy)}</td><td>{money(p.cost_gbp)}</td><td>{money(p.comparison_cost_gbp)} · {p.comparison_eligible ? "eligible" : "excluded"}</td></tr>)}</tbody></table></div></details></section>
    <section className="agent-panel" aria-label="Source uncertainty"><h2>Evidence and uncertainty</h2>{uncertainty.human_question && <p role="alert"><strong>{uncertainty.human_question}</strong></p>}{uncertainty.reported_delay_range && <p>Fresh source reports imply a {uncertainty.reported_delay_range.join("–")}-day delay range. These are source claims, not a statistical confidence interval.</p>}{uncertainty.updates.length === 0 && <p>No additional carrier/supplier update is attached to this case. The injected delay is a hypothetical assumption.</p>}{uncertainty.updates.map(u => <details key={u.update_id}><summary>{u.source} · arrival {u.reported_arrival} · {u.stale ? "stale" : "fresh"}</summary><p>{u.description}</p><p>Observed {u.observed_at_utc}; treated as untrusted source data.</p></details>)}<ProvenanceView value={assessment.provenance} /></section>
  </>;
}

export default function SubmissionWorkbench() {
  const [cases,setCases] = useState<Case[]>([]);
  const [suppliers,setSuppliers] = useState<Supplier[]>([]);
  const [status,setStatus] = useState<Status | null>(null);
  const [input,setInput] = useState<Input>({supplier_id:"SUP-ALPHA",delay_days:5,case_id:"alpha-delay",max_action_cost_gbp:null,max_late_days:null,compare_strategy:"alternative_supplier"});
  const [budget,setBudget] = useState("");
  const [decision,setDecision] = useState<Decision | null>(null);
  const [decisionInput,setDecisionInput] = useState("");
  const [run,setRun] = useState<Run | null>(null);
  const [history,setHistory] = useState<{id:string;status:string}[]>([]);
  const [historyComparison,setHistoryComparison] = useState<unknown>(null);
  const [error,setError] = useState("");
  const [busy,setBusy] = useState(false);
  const [note,setNote] = useState("");
  const [reload,setReload] = useState(0);
  const currentInput = {...input,max_action_cost_gbp:budget === "" ? null : budget.includes(".") ? budget.split(".")[0]+"."+budget.split(".")[1].padEnd(2,"0") : budget+".00"};
  useEffect(() => {
    const controller = new AbortController();
    const signal=controller.signal;
    request<Case[]>("/api/v2/cases",{signal}).then(setCases).catch(e=>{if(!signal.aborted)setError(String(e));});
    request<{suppliers:Supplier[]}>("/api/v2/workspace",{signal},90_000).then(v=>setSuppliers(v.suppliers)).catch(e=>{if(!signal.aborted)setError(String(e));});
    request<Status>("/api/v2/status",{signal},90_000).then(setStatus).catch(e=>{if(!signal.aborted)setError(String(e));});
    request<{id:string;status:string}[]>("/api/v2/investigation-runs",{signal}).then(setHistory).catch(()=>{});
    return ()=>controller.abort();
  },[reload]);
  useEffect(() => {
    if(!run || terminal.has(run.status)) return;
    const controller=new AbortController();
    const timer=window.setInterval(()=>{request<Run>(`/api/v2/investigation-runs/${run.id}`,{signal:controller.signal}).then(setRun).catch(e=>{if(!controller.signal.aborted)setError(String(e));});},1000);
    return ()=>{window.clearInterval(timer);controller.abort();};
  },[run?.id,run?.status]);

  async function execute(ai:boolean) {
    setError("");setBusy(true);
    try {
      if(ai) setRun(await request<Run>("/api/v2/investigation-runs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(currentInput)}));
      else {const result=await request<Decision>("/api/v2/simulations",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(currentInput)},90_000);setDecision(result);setDecisionInput(JSON.stringify(currentInput));}
    } catch(e){setError(e instanceof Error?e.message:String(e));} finally{setBusy(false);}
  }
  async function review(action:string){if(!run)return;try{setRun(await request<Run>(`/api/v2/investigation-runs/${run.id}/review`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action,note})}));}catch(e){setError(String(e));}}
  const report=run?.report;
  return <div className="workspace"><aside className="sidebar"><a href="#scenario" className="brand">Sentry AI</a><div className="sidebar-label">SUPPLY CHAIN INVESTIGATIONS</div><nav aria-label="Workspace navigation"><a className="nav-link" href="#scenario">Scenario & constraints</a><a className="nav-link" href="#investigation">Agent investigation</a><a className="nav-link" href="#results">Decision evidence</a></nav><div className="sidebar-note"><p>Know why. Know what would change it.</p><p>Track 2 · Open Agent Hackathon 2026</p></div></aside><main className="main-content"><div className="page-content">
    <header className="page-heading"><div><div className="eyebrow">DISRUPTION → EVIDENCE → DECISION</div><h1>When a supplier slips, know your next move.</h1><p>Investigate the facts. Compare recovery choices. Keep the decision accountable.</p></div></header>
    <section className="agent-panel" aria-label="Integration status"><h2>Connected services</h2><p>Data: <strong>{status?.data_mode ?? "checking"}</strong> · Zetaris: {status?.zetaris.status ?? "checking"} · Nightshift: {status?.nightshift.status ?? "checking"} · H-MEM: {status?.hmem.status ?? "checking"}</p><p>Synthetic business data · fixed evaluation date 25 October 2026. Model discovery is not proof that inference is ready; the run report records actual usage.</p><button className="text-button" onClick={()=>setReload(v=>v+1)}>Refresh connections and history</button><details><summary>Connection details</summary><pre>{JSON.stringify(status,null,2)}</pre></details></section>
    <section className="agent-panel" id="scenario"><h2>Build your scenario</h2><div className="v2-controls">
      <label>Demonstration case<select aria-label="Demonstration case" value={input.case_id} onChange={e=>{const c=cases.find(c=>c.case_id===e.target.value);if(c){setInput({...input,case_id:c.case_id,supplier_id:c.supplier_id,delay_days:c.delay_days,max_action_cost_gbp:c.max_action_cost_gbp??null,max_late_days:c.max_late_days??null});setBudget(c.max_action_cost_gbp??"");}}}>{cases.map(c=><option key={c.case_id} value={c.case_id}>{c.name}</option>)}</select></label>
      <label>Supplier<select aria-label="Supplier" disabled={!suppliers.length} value={input.supplier_id} onChange={e=>setInput({...input,supplier_id:e.target.value})}>{suppliers.map(s=><option key={s.supplier_id} value={s.supplier_id}>{s.name} · {s.supplier_id}</option>)}</select></label>
      <label>Supplier delay: {input.delay_days} days<input type="range" min="0" max="30" value={input.delay_days} onChange={e=>setInput({...input,delay_days:Number(e.target.value)})}/></label>
      <label>Maximum intervention spending (£, optional)<input type="number" min="0" step="0.01" value={budget} onChange={e=>setBudget(e.target.value)}/></label>
      <label>Maximum remaining lateness (days, optional)<input type="number" min="0" max="60" value={input.max_late_days??""} onChange={e=>setInput({...input,max_late_days:e.target.value===""?null:Number(e.target.value)})}/></label>
      <label>Compare against<select aria-label="Compare against" value={input.compare_strategy} onChange={e=>setInput({...input,compare_strategy:e.target.value as Strategy})}>{Object.entries(strategyLabels).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
    </div><div className="v2-actions"><button className="run-button" disabled={busy||!suppliers.length} onClick={()=>execute(false)}>Compare calculated options</button><button className="run-button" disabled={busy||!suppliers.length||!!run&&!terminal.has(run.status)} onClick={()=>execute(true)}>Run AI investigation</button></div></section>
    {error&&<div className="agent-error" role="alert">{error}</div>}
    {decision&&<div id="results">{decisionInput!==JSON.stringify(currentInput)&&<p role="status">Calculated results belong to the last submitted inputs. Rerun to apply current controls.</p>}<DecisionView assessment={decision} sweep={decision.counterfactuals} uncertainty={decision.uncertainty}/></div>}
    <section className="agent-panel" id="investigation" aria-label="AI investigation"><h2>Agent investigation</h2><p>Planner and Investigator use Nightshift. A model Critic challenges the draft. The deterministic Evaluator blocks unsupported figures and sends evidence gaps back for more work.</p>
      {run&&<><p><strong>Run status: {run.status}</strong> · {run.id} · {run.request.supplier_id} +{run.request.delay_days} days</p>{JSON.stringify(run.request)!==JSON.stringify(currentInput)&&<p>The report refers to the recorded run inputs, not the current controls.</p>}{!terminal.has(run.status)&&<button className="text-button" onClick={async()=>{try{setRun(await request<Run>(`/api/v2/investigation-runs/${run.id}/cancel`,{method:"POST"}));}catch(e){setError(String(e));}}}>Cancel investigation</button>}{run.cancelled&&!terminal.has(run.status)?<p>Cancellation requested. Waiting for the active model call to finish.</p>:null}{run.error&&<p role="alert">{run.error}</p>}
      <details open={!terminal.has(run.status)}><summary>Live collaboration trace · {run.events.length} events</summary><ol>{run.events.map((e,i)=><li key={i}><strong>{e.agent}</strong> · {e.message} <small>{e.at}</small></li>)}</ol></details>
      {report&&<><h3>{report.status==="validated"?"AI recommendation validated":"Recommendation withheld"}</h3>{report.recommended_strategy&&<p><strong>{label(report.recommended_strategy)}</strong></p>}<p>{report.explanation??report.validation.unresolved.join("; ")}</p><p>{report.model?.calls??0} model calls · {report.model?.models_used.join(", ")??"no model needed"} · {report.model?.signed_receipts??0} signed receipts</p><p>Memory: {report.memory?.recalled.length??0} recalled · {report.memory?.stored_memory_id?"validated finding saved":"no new validated memory"}</p><details><summary>Plan, rejected drafts and critiques</summary><pre>{JSON.stringify({plan:report.plan,attempts:report.attempts,critiques:report.critiques,validation:report.validation},null,2)}</pre></details><details><summary>Source evidence, tools and receipts</summary><pre>{JSON.stringify({evidence_ids:report.supporting_evidence_ids,tools:report.tool_calls,model:report.model},null,2)}</pre></details><details><summary>Memory, feedback and conflicts</summary><pre>{JSON.stringify(report.memory,null,2)}</pre></details><DecisionView assessment={report.decision} sweep={report.counterfactuals} uncertainty={report.uncertainty}/><p>{report.disclaimer}</p></>}
      {terminal.has(run.status)&&<><div className="v2-actions"><a href={`/api/v2/investigation-runs/${run.id}/export?format=json`} download>Download JSON decision packet</a><a href={`/api/v2/investigation-runs/${run.id}/export?format=markdown`} download>Download Markdown packet</a></div><label>Review note<textarea value={note} onChange={e=>setNote(e.target.value)} maxLength={1200}/></label><div className="v2-actions"><button disabled={run.status!=="validated"} onClick={()=>review("approve")}>Approve recommendation</button><button onClick={()=>review("request_revision")}>Request revision</button><button onClick={()=>review("defer")}>Defer decision</button></div><p>Human review records a decision only. It never executes a purchase or shipment.</p>{run.review?.map((r,i)=><p key={i}>{r.action}: {r.note} · {r.effect}</p>)}</>}
      </>}
      {!run&&<p>Choose a scenario, then start an investigation. Progress and results come from the real backend.</p>}
      <details><summary>Previous investigations</summary>{history.map(h=><p key={h.id}><button className="text-button" onClick={async()=>{try{setRun(await request<Run>(`/api/v2/investigation-runs/${h.id}`));}catch(e){setError(String(e));}}}>{h.id} · {h.status}</button>{run&&h.id!==run.id&&<button className="text-button" onClick={async()=>{try{setHistoryComparison(await request(`/api/v2/investigation-runs/${run.id}/comparison?against=${h.id}`));}catch(e){setError(String(e));}}}>Compare with current run</button>}</p>)}</details>{historyComparison!==null&&<details open><summary>Recorded investigation comparison</summary><pre>{JSON.stringify(historyComparison,null,2)}</pre></details>}
    </section><footer className="footer">Synthetic cases · exact calculated finance · evidence-linked AI · human decisions. <a href="/legacy">Original simulator</a></footer>
  </div></main></div>;
}
