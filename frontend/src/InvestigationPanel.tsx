import { useEffect, useRef, useState } from "react";
import { request } from "./api";
import { strategyLabels } from "./format";
import type { Strategy } from "./types";

interface Investigation {
  investigation_id: string;
  status: "validated" | "unresolved";
  incident: { supplier_id: string; delay_days: number };
  recommended_strategy: Strategy | null;
  explanation: string | null;
  supporting_evidence_ids: string[];
  data_source: string;
  disclaimer: string;
  validation: {
    attempts_used: number;
    checks: { check: string; passed: boolean; detail: string }[];
    unresolved: string[];
  };
  plan: { task_id: string; question: string; tool: string }[];
  tool_calls: { call_id: string; tool: string; status: string; summary: string; evidence_ids: string[]; result: unknown }[];
  model: { models_used: string[]; calls: number; receipt_ids: string[]; signed_receipts: number };
  memory: { engine: string; recalled: { memory_id: string; content: string }[]; stored_memory_id: string | null } | null;
}

export default function InvestigationPanel({ supplierId, delayDays }: { supplierId: string; delayDays: number }) {
  const [report, setReport] = useState<Investigation | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const active = useRef<AbortController | null>(null);

  useEffect(() => {
    setReport(null);
    setError("");
    setRunning(false);
    return () => { active.current?.abort(); };
  }, [supplierId, delayDays]);

  async function investigate() {
    if (running || !supplierId) return;
    const controller = new AbortController();
    active.current = controller;
    setRunning(true);
    setReport(null);
    setError("");
    try {
      const result = await request<Investigation>("/api/investigations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ supplier_id: supplierId, delay_days: delayDays }),
        signal: controller.signal,
      }, 240_000);
      if (!controller.signal.aborted) setReport(result);
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "Investigation failed.");
    } finally {
      if (active.current === controller) setRunning(false);
    }
  }

  return <section className="agent-panel" aria-labelledby="agent-title" id="investigation">
    <div className="agent-heading">
      <div><span className="eyebrow">INVESTIGATE WITH AI</span><h2 id="agent-title">Ask Sentry to explain why</h2></div>
      <button className="run-button" disabled={running || !supplierId} onClick={investigate}>
        {running ? "Investigating…" : "Run AI investigation"}
      </button>
    </div>
    <p>Nightshift plans an investigation, runs evidence tools and drafts a recommendation. The evaluator checks it against calculated costs. H-MEM recalls and saves validated findings.</p>
    <p className="agent-scope">Selected scenario: {supplierId || "choose a supplier"} · +{delayDays} days · synthetic data. Requires a configured Nightshift runtime.</p>
    {running && <div role="status">Waiting for Nightshift and validation. This may take several minutes. Changing the scenario stops waiting here; server work may continue.</div>}
    {error && <div className="agent-error" role="alert"><strong>AI investigation unavailable</strong><p>{error}</p><p>The calculated simulator remains available. No AI answer was substituted.</p></div>}
    {report && <div className="agent-report" aria-live="polite">
      <h3>{report.status === "validated" ? "AI recommendation validated" : "Investigation unresolved"}</h3>
      {report.status === "validated" && report.recommended_strategy && <><p><strong>{strategyLabels[report.recommended_strategy]}</strong></p><p>{report.explanation}</p></>}
      {report.status === "unresolved" && <><p>The model did not pass validation. No AI recommendation was accepted.</p><ul>{report.validation.unresolved.map((reason, i) => <li key={i}>{reason}</li>)}</ul></>}
      <p>{report.validation.attempts_used} draft(s) · {report.model.calls} model calls · {report.model.models_used.join(", ")} · {report.model.signed_receipts} signed receipt(s)</p>
      <p>Memory: {report.memory ? `${report.memory.recalled.length} recalled; ${report.memory.stored_memory_id ? "validated finding saved" : "no finding saved"}` : "not used"}. Data source: {report.data_source}.</p>
      <details><summary>Investigation plan</summary><ol>{report.plan.map(step => <li key={step.task_id}>{step.question} ({step.tool})</li>)}</ol></details>
      <details><summary>Evidence and tool results</summary>{report.tool_calls.map(call => <details key={call.call_id}><summary>{call.tool} · {call.status}</summary><p>{call.summary}</p><p>{call.evidence_ids.join(", ")}</p><pre>{JSON.stringify(call.result, null, 2)}</pre></details>)}<p>Supporting evidence: {report.supporting_evidence_ids.join(", ") || "none validated"}</p></details>
      <details><summary>Validation checks</summary><ul>{report.validation.checks.map(check => <li key={check.check}>{check.passed ? "Passed" : "Failed"}: {check.check} — {check.detail}</li>)}</ul></details>
      {report.memory && report.memory.recalled.length > 0 && <details><summary>Recalled memory</summary>{report.memory.recalled.map(item => <p key={item.memory_id}>{item.content}</p>)}</details>}
      <details><summary>Model receipts</summary><ul>{report.model.receipt_ids.map((id, i) => <li key={`${id}-${i}`}>{id}</li>)}</ul></details>
      <p className="agent-scope">{report.disclaimer} Run: {report.investigation_id}.</p>
    </div>}
  </section>;
}
