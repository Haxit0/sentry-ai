import { useState } from "react";
import type { Sweep, Run } from "./workbenchTypes";
import type { Strategy } from "./types";
import { strategyLabels } from "./format";

const paths: Record<string, string> = {
  shield: "M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z M9 12l2 2 4-5",
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  activity: "M3 12h4l3-8 4 16 3-8h4",
  chart: "M4 3v17h17 M8 15l4-5 4 2 5-7",
  history: "M3 11a9 9 0 1 1 2 7 M3 4v7h7 M12 7v6l4 2",
  database: "M20 6c0 2-16 2-16 0s16-2 16 0ZM4 6v12c0 3 16 3 16 0V6 M4 12c0 3 16 3 16 0",
  arrow: "M4 12h16 M14 6l6 6-6 6",
  chevron: "m9 5 7 7-7 7",
  down: "m6 9 6 6 6-6",
  check: "m5 12 4 4L19 6",
  close: "m6 6 12 12 M6 18 18 6",
  info: "M12 8h.01 M12 11v6 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  download: "M12 3v12 m-5-5 5 5 5-5 M4 16v5h16v-5",
  truck: "M3 5h11v12H3z M14 9h4l3 4v4h-7 M6 17a2 2 0 1 0 .01 0 M17 17a2 2 0 1 0 .01 0",
  package: "m12 3 9 5-9 5-9-5 9-5Z M3 8v10l9 5 9-5V8 M12 13v10 M7 5l10 6",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z",
  refresh: "M20 7v5h-5 M4 17v-5h5 M5 7a8 8 0 0 1 14-1l1 6 M4 12l1 6a8 8 0 0 0 14-1",
  search: "M20 20l-5-5 M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z",
  menu: "M4 6h16 M4 12h16 M4 18h16",
};

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] ?? paths.info} /></svg>;
}

export const currency = (value: string | null | undefined) => value == null ? "—" : new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(Number(value));
export const shortDate = (value: string) => new Date(value.length === 10 ? value + "T00:00:00Z" : value).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
export const policyName = (value: Strategy | null) => value ? strategyLabels[value] : "No feasible recovery";

export function DelayChart({ sweep, currentDelay }: { sweep: Sweep; currentDelay: number }) {
  const [inspect, setInspect] = useState(currentDelay);
  const point = sweep.points[inspect] ?? sweep.points[0];
  const maximum = Math.max(1, ...sweep.points.flatMap(p => [Number(p.cost_gbp ?? 0), Number(p.comparison_cost_gbp)]));
  const x = (day: number) => 42 + day * (650 / 30);
  const y = (cost: string | null) => 154 - Number(cost ?? 0) / maximum * 125;
  const line = sweep.points.map((p, i) => p.cost_gbp === null ? "" : `${i === 0 || sweep.points[i - 1].cost_gbp === null ? "M" : "L"}${x(p.delay_days)},${y(p.cost_gbp)}`).join(" ");
  return <div className="sw-chart">
    <div className="sw-chart-inspect"><span><span className="sw-dot" />Best eligible recovery</span><span className="sw-chart-alternative">Selected alternative</span><strong>{inspect} days · {currency(point.cost_gbp)}</strong></div>
    <svg viewBox="0 0 730 190" role="img" aria-label="Calculated recovery costs across zero to thirty hypothetical delay days">
      {[0, 0.5, 1].map(f => <g key={f}><line x1="42" x2="692" y1={154 - f * 125} y2={154 - f * 125} stroke="#e6eae8" strokeDasharray="3 5" /><text x="35" y={158 - f * 125} textAnchor="end" fill="#64736f" fontSize="10">£{Math.round(maximum * f)}</text></g>)}
      <polyline points={sweep.points.map(p => `${x(p.delay_days)},${y(p.comparison_cost_gbp)}`).join(" ")} fill="none" stroke="#96a6b8" strokeWidth="2" strokeDasharray="5 5" />
      <path d={line} fill="none" stroke="#137c66" strokeWidth="3" strokeLinejoin="round" />
      <line x1={x(inspect)} x2={x(inspect)} y1="20" y2="154" stroke="#137c66" strokeDasharray="3 4" opacity=".5" />
      {point.cost_gbp !== null && <circle cx={x(inspect)} cy={y(point.cost_gbp)} r="5" fill="#137c66" stroke="white" strokeWidth="3" />}
      {[0, 5, 10, 15, 20, 25, 30].map(d => <text key={d} x={x(d)} y="178" textAnchor="middle" fill="#64736f" fontSize="11">{d}d</text>)}
    </svg>
    <label className="sw-chart-slider">Explore delay <input aria-label="Explore calculated delay" type="range" min="0" max="30" value={inspect} onChange={e => setInspect(Number(e.target.value))} /><strong>{inspect} days</strong></label>
    <p className="sw-chart-caption">{policyName(point.strategy)} · {currency(point.cost_gbp)} total. Exploring this chart does not change your scenario.</p>
  </div>;
}

const eventNames: Record<string, string> = { data: "Evidence acquired", planner: "Planner", investigator: "Investigator", critic: "Critic", evaluator: "Evaluator", memory: "H-MEM memory", tool: "Evidence tool", feedback: "Feedback & revision", operator: "Operator" };
export function AgentTimeline({ run }: { run: Run }) {
  const active = !["validated", "unresolved", "cancelled", "failed"].includes(run.status);
  const roles = [
    { role: "planner", title: "Plan", detail: "Choose the questions" },
    { role: "tool", title: "Investigate", detail: "Gather source evidence" },
    { role: "critic", title: "Challenge", detail: "Check the explanation" },
    { role: "evaluator", title: "Validate", detail: "Verify costs & citations" },
  ];
  return <>
    <div className="sw-agent-stages">{roles.map((r, i) => {
      const seen = run.events.some(e => e.agent === r.role);
      const complete = run.status === "validated" || seen;
      return <div key={r.role} className={complete ? "is-done" : ""}><span className="sw-stage-icon">{complete ? <Icon name="check" size={15} /> : i + 1}</span><span><strong>{r.title}</strong><small>{r.detail}</small></span></div>;
    })}</div>
    <details className="sw-trace" open={active}><summary>Live collaboration trace · {run.events.length} events <Icon name="down" size={16} /></summary>
      <ol className="sw-timeline">{run.events.map((e, i) => <li key={i}><span className={`sw-event-point ${e.agent === "feedback" ? "is-feedback" : ""}`} /><div><strong>{eventNames[e.agent] ?? e.agent}</strong><p>{e.message}</p></div><time>{Number.isNaN(Date.parse(e.at)) ? "" : new Date(e.at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time></li>)}</ol>
      {run.events.length === 0 && <p className="sw-muted">Your investigation is queued. Events will appear as work starts.</p>}
    </details>
  </>;
}
