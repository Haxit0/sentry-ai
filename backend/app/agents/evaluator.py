"""Evaluator agent: verifies the investigator's claim before anything is recommended.

Deterministic on purpose: every check compares the model's claim with tool outputs and the
exact Decimal simulation. A failed check becomes an explicit retry reason; nothing is waved through.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.agents.planner import REQUIRED_TOOLS
from app.agents.schemas import Check, Claim
from app.agents.tools import InvestigationTools

MONEY_IN_TEXT = re.compile(r"(?:£|GBP\s*)(\d[\d,]*(?:\.\d{1,2})?)", re.IGNORECASE)
ORDER_IN_TEXT = re.compile(r"\bORD-\d+\b")
PERCENT_IN_TEXT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|per\s?cent)", re.IGNORECASE)
SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Evaluation:
    checks: list[Check]
    feedback: list[str] = field(default_factory=list)
    missing_tools: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed(self) -> list[str]:
        return [check.check for check in self.checks if not check.passed]


def parse_money(value: str | None) -> Decimal | None:
    if value is None:
        return None
    text = str(value).replace("£", "").replace(",", "").replace("GBP", "").strip()
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    return amount if amount.is_finite() else None


def evaluate(claim: Claim, tools: InvestigationTools) -> Evaluation:
    result = tools.simulation
    evidence = tools.evidence_index()
    order_ids = {order.order_id for order in tools.data.orders}
    options = {option.strategy: option for option in result.recovery_options}
    affected = {order.order_id for order in result.affected_orders}
    evaluation = Evaluation(checks=[])

    def check(name: str, passed: bool, detail: str, fix: str | None = None) -> None:
        evaluation.checks.append(Check(check=name, passed=passed, detail=detail))
        if not passed and fix:
            evaluation.feedback.append(fix)

    missing = [tool for tool in REQUIRED_TOOLS if not tools.called(tool)]
    evaluation.missing_tools = missing
    check("required_tools_called", not missing,
          "all required tools returned data" if not missing else f"missing tool results: {', '.join(missing)}")

    strategy = claim.recommended_strategy
    check("strategy_exists", strategy in options, f"claimed {strategy!r}; options {sorted(options)}",
          f"recommended_strategy must be one of {sorted(options)}")
    check("strategy_matches_calculation", strategy == result.recommended_strategy,
          f"claimed {strategy!r}; deterministic ranking puts {result.recommended_strategy} first",
          f"the cheapest option in get_recovery_options is {result.recommended_strategy}")

    unknown = [order_id for order_id in claim.affected_order_ids if order_id not in order_ids]
    check("order_ids_valid", not unknown, "all claimed order ids exist" if not unknown else f"unknown order ids: {unknown}",
          f"these order ids do not exist: {unknown}")
    claimed = set(claim.affected_order_ids)
    check("affected_orders_match", claimed == affected,
          f"claimed {sorted(claimed)}; simulation found {sorted(affected)}",
          f"affected_order_ids must be exactly {sorted(affected)} (late orders in run_disruption_simulation)")

    exposure = parse_money(claim.penalty_exposure_gbp)
    check("exposure_matches", exposure == result.estimated_penalty_exposure_gbp,
          f"claimed {claim.penalty_exposure_gbp!r}; calculated {result.estimated_penalty_exposure_gbp:.2f}",
          f"penalty_exposure_gbp must be copied from the tool output: {result.estimated_penalty_exposure_gbp:.2f}")
    cost = parse_money(claim.recommended_total_cost_gbp)
    expected_cost = options[strategy].total_estimated_cost_gbp if strategy in options else None
    check("cost_matches", expected_cost is not None and cost == expected_cost,
          f"claimed {claim.recommended_total_cost_gbp!r}; calculated "
          f"{f'{expected_cost:.2f}' if expected_cost is not None else 'n/a (unknown strategy)'}",
          f"recommended_total_cost_gbp must be the total_gbp of the recommended option"
          + (f": {expected_cost:.2f}" if expected_cost is not None else ""))

    looked_up = {c.arguments.get("evidence_id"): c.status for c in tools.calls if c.tool == "get_evidence"}
    absent = [e for e in claim.evidence_ids if e not in evidence or looked_up.get(e) not in (None, "ok")]
    check("evidence_exists", bool(claim.evidence_ids) and not absent,
          "no evidence cited" if not claim.evidence_ids else
          ("every cited evidence id resolved via get_evidence" if not absent else f"unresolvable evidence ids: {absent}"),
          f"cite only evidence_ids from the tool outputs; these do not exist: {absent}" if absent
          else "cite the evidence_ids that support the recommendation")
    needed = {f"order:{order_id}" for order_id in affected} | {f"recovery:{result.supplier_id}"}
    uncited = sorted(needed - set(claim.evidence_ids))
    check("evidence_supports_recommendation", not uncited,
          "recovery offer and every affected order are cited" if not uncited else f"supporting evidence not cited: {uncited}",
          f"also cite {uncited}")

    allowed = _known_figures(tools)
    stated = [parse_money(m) for m in MONEY_IN_TEXT.findall(claim.explanation)]
    invented = sorted({f"{amount:.2f}" for amount in stated if amount is not None and amount not in allowed})
    # No tool returns a percentage, so any percentage is model arithmetic.
    invented += [f"{p}%" for p in PERCENT_IN_TEXT.findall(claim.explanation)]
    # The explanation is about impact, so it may only name orders the simulation found late.
    bad_orders = sorted(set(ORDER_IN_TEXT.findall(claim.explanation)) - affected)
    offending = [s for s in SENTENCE.split(claim.explanation) if PERCENT_IN_TEXT.search(s)
                 or any(o in s for o in bad_orders)
                 or any((a := parse_money(m)) is not None and a not in allowed for m in MONEY_IN_TEXT.findall(s))]
    check("explanation_grounded", bool(claim.explanation) and not invented and not bad_orders,
          "empty explanation" if not claim.explanation else
          (f"figures not in tool outputs: {invented}; orders named but not late: {bad_orders}" if invented or bad_orders
           else "every figure and order in the explanation comes from tool outputs"),
          "rewrite the explanation without these sentences, which state figures absent from the tool outputs or name "
          f"orders that are not late (late orders: {sorted(affected) or 'none'}): "
          + " | ".join(f'"{s.strip()}"' for s in offending) + ". Use only GBP figures copied from the tool outputs and no percentages"
          if claim.explanation else "write a 2-4 sentence explanation")
    return evaluation


def _known_figures(tools: InvestigationTools) -> set[Decimal]:
    result = tools.simulation
    supplier = tools.supplier
    figures = {result.estimated_penalty_exposure_gbp}
    for option in result.recovery_options:
        figures |= {option.residual_penalty_gbp, option.action_cost_gbp, option.total_estimated_cost_gbp,
                    abs(option.saving_vs_no_action_gbp)}
    for order in result.affected_orders:
        figures |= {order.estimated_penalty_gbp, order.penalty_per_day_gbp}
    figures |= {supplier.expedite.fixed_fee_gbp, supplier.expedite.per_unit_fee_gbp,
                supplier.alternative.fixed_fee_gbp, supplier.alternative.unit_premium_gbp}
    return figures
