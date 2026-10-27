import type { Assessment } from "./workbenchTypes";
import type { Strategy } from "./types";
import { currency } from "./WorkbenchVisuals";

const names: Record<Strategy,string> = {expedite_shipping:"Speed up the shipment",alternative_supplier:"Use another supplier",accept_delay:"Keep the current plan"};
const pennies = (value:string) => { const [whole,part=""] = value.split("."); return BigInt(whole)*100n+BigInt(part.padEnd(2,"0")); };
const amount = (value:bigint) => `${value/100n}.${(value%100n).toString().padStart(2,"0")}`;

/** Explain only the returned calculations; never invent carrier quotes or AI findings. */
export function DecisionReasons({assessment}:{assessment:Assessment}) {
  const chosen=assessment.options.find(o=>o.strategy===assessment.recommendation);
  if(!chosen)return null;
  return <div className="gu-tradeoffs" role="region" aria-label="Why this option">
    <h3>Why this option?</h3>
    <ul>{assessment.options.filter(o=>o.strategy!==chosen.strategy).map(other=>{
      const extra=pennies(other.total_estimated_cost_gbp)-pennies(chosen.total_estimated_cost_gbp);
      const late=other.max_remaining_late_days;
      let reason:string;
      if(!other.eligible)reason=other.exclusion_reasons.map(r=>r.includes("spending")?"Over your spending limit":r.includes("lateness")?"Misses your delivery limit":r).join(". ")+".";
      else if(extra>0n) reason=late<chosen.max_remaining_late_days?`${currency(amount(extra))} more, but reduces the worst lateness to ${late} days.`:late>chosen.max_remaining_late_days?`${currency(amount(extra))} more, with up to ${late} days of lateness.`:`${currency(amount(extra))} more, with the same remaining lateness.`;
      else if(extra===0n) reason="Same total cost. The consistent tie-break order favors the chosen plan.";
      else reason="Lower price, but review its limits before changing the plan.";
      return <li key={other.strategy}><div><strong>{names[other.strategy]}</strong><span>{currency(other.total_estimated_cost_gbp)} total</span></div><p>{reason}</p></li>;
    })}</ul>
  </div>;
}

export function PublicDraftFeedback({attempts}:{attempts:unknown[]}) {
  return <div className="gu-public-drafts">{attempts.map((raw,i)=>{
    const row=raw&&typeof raw==="object"?raw as Record<string,unknown>:{};
    const feedback=Array.isArray(row.feedback)?row.feedback.filter((v):v is string=>typeof v==="string"):[];
    return <article key={i}><strong>Draft {i+1} · {typeof row.outcome==="string"?row.outcome.replaceAll("_"," "):"reviewed"}</strong>{feedback.length?<ul>{feedback.map((f,j)=><li key={j}>{f}</li>)}</ul>:<p>No correction was requested for this draft.</p>}</article>;
  })}</div>;
}
