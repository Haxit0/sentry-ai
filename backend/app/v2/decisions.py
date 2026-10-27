"""Constraint-aware policy comparison and counterfactuals use exact backend arithmetic."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import Field, StrictInt
from app.schemas import Cost, SimulationRequest, Strategy
from app.services.simulation import simulate_with_lateness

class DecisionRequest(SimulationRequest):
    case_id: str = Field(default="alpha-delay", max_length=60)
    max_action_cost_gbp: Cost | None = None
    max_late_days: StrictInt | None = Field(default=None, ge=0, le=60)
    compare_strategy: Strategy = "alternative_supplier"

CASES = [
    {"case_id": "alpha-delay", "name": "Sensor shipment delayed five days", "supplier_id": "SUP-ALPHA", "delay_days": 5},
    {"case_id": "no-delay", "name": "No disruption: avoid unnecessary spending", "supplier_id": "SUP-ALPHA", "delay_days": 0},
    {"case_id": "long-delay", "name": "A long delay changes the best recovery", "supplier_id": "SUP-ALPHA", "delay_days": 30},
    {"case_id": "limited-capacity", "name": "Recovery capacity cannot cover every order", "supplier_id": "SUP-BETA", "delay_days": 5},
    {"case_id": "budget-blocked", "name": "No option meets both budget and deadline", "supplier_id": "SUP-ALPHA", "delay_days": 5, "max_action_cost_gbp": "50.00", "max_late_days": 0},
    {"case_id": "conflicting-eta", "name": "Supplier and carrier disagree on arrival", "supplier_id": "SUP-ALPHA", "delay_days": 5},
    {"case_id": "stale-update", "name": "An old arrival report needs confirmation", "supplier_id": "SUP-ALPHA", "delay_days": 5},
    {"case_id": "injected-note", "name": "A source note contains an untrusted instruction", "supplier_id": "SUP-ALPHA", "delay_days": 5},
]

def compare(request, snapshot):
    result, late = simulate_with_lateness(SimulationRequest(supplier_id=request.supplier_id, delay_days=request.delay_days), snapshot)
    policies = []
    for item in result.recovery_options:
        reasons = []
        if request.max_action_cost_gbp is not None and item.action_cost_gbp > request.max_action_cost_gbp:
            reasons.append("Intervention spending exceeds the budget")
        if request.max_late_days is not None and late[item.strategy] > request.max_late_days:
            reasons.append("Remaining order lateness exceeds the limit")
        policies.append({**item.model_dump(mode="json"), "max_remaining_late_days": late[item.strategy],
                         "eligible": not reasons, "exclusion_reasons": reasons,
                         "evidence_ids": [f"supplier:{request.supplier_id}", f"recovery:{request.supplier_id}"]})
    selected = next((p for p in policies if p["eligible"]), None)
    return {"simulation": result.model_dump(mode="json"), "options": policies,
            "recommendation": selected["strategy"] if selected else None,
            "feasibility": "feasible" if selected else "no_feasible_recovery",
            "constraints": {"max_action_cost_gbp": f"{request.max_action_cost_gbp:.2f}" if request.max_action_cost_gbp is not None else None,
                            "max_late_days": request.max_late_days}, "provenance": snapshot.provenance}

def uncertainty(request, snapshot):
    # Demo observations are assessed against their explicit frozen evaluation clock, not today's wall clock.
    reference = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
    rows, stale, arrivals = [], [], []
    for item in snapshot.updates:
        if item["supplier_id"] != request.supplier_id:
            continue
        observed = datetime.fromisoformat(item["observed_at_utc"].replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError("Supply update timestamps must include a timezone")
        is_stale = (reference-observed).total_seconds() > int(item["freshness_hours"])*3600 or observed > reference
        rows.append({**item, "stale": is_stale, "evidence_id": f"update:{item['update_id']}"})
        if is_stale:
            stale.append(item["update_id"])
        else:
            arrivals.append(item["reported_arrival"])
    conflict = len(set(arrivals)) > 1
    blocked = conflict or bool(rows and len(stale) == len(rows))
    bounds = None
    if arrivals:
        supplier = next(s for s in snapshot.data.suppliers if s.supplier_id == request.supplier_id)
        base = datetime.fromisoformat(str(supplier.restock_date))
        delays = [(datetime.fromisoformat(a)-base).days for a in arrivals]
        bounds = [max(0, min(30, min(delays))), max(0, min(30, max(delays)))]
    return {"updates": rows, "conflicting_arrival_estimates": conflict, "stale_update_ids": stale,
            "blocks_recommendation": blocked, "reported_delay_range": bounds,
            "reference_time_utc": reference.isoformat(),
            "human_question": "Confirm the current expected arrival with the supplier and carrier." if blocked else None}

def counterfactuals(request, snapshot):
    points = []
    for delay in range(31):
        decision = compare(request.model_copy(update={"delay_days": delay}), snapshot)
        selected = next((p for p in decision["options"] if p["strategy"] == decision["recommendation"]), None)
        alternative = next(p for p in decision["options"] if p["strategy"] == request.compare_strategy)
        points.append({"delay_days": delay, "strategy": decision["recommendation"], "cost_gbp": selected["total_estimated_cost_gbp"] if selected else None,
                       "comparison_strategy": request.compare_strategy, "comparison_cost_gbp": alternative["total_estimated_cost_gbp"],
                       "comparison_eligible": alternative["eligible"]})
    current = points[request.delay_days]["strategy"]
    change = next((p for p in points[request.delay_days+1:] if p["strategy"] != current), None)
    evidence = uncertainty(request, snapshot)
    bounded = [points[d] for d in range(evidence["reported_delay_range"][0], evidence["reported_delay_range"][1]+1)] if evidence["reported_delay_range"] else []
    return {"points": points, "first_change_after_selected_delay": change,
            "arrival_range_outcomes": bounded, "assumption": "Injected calendar-day delay; a hypothetical sweep, not a forecast.", "provenance": snapshot.provenance}
