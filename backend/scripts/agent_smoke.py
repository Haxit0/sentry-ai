"""Live agent smoke test: real Nightshift inference plus the real Meterless H-MEM engine.

Usage, from `backend`:
    python -m scripts.agent_smoke [--out report.json] [--memory-dir DIR] [--zetaris]

Runs Alpha +5 (golden scenario), then Alpha +6 against the same H-MEM store, so the second
investigation must recall the first. A fresh temporary store is used unless --memory-dir is given.
Prints routing, receipts, tool calls, validation and memory operations; never prints the token.
Exits non-zero if inference fails, validation fails, or the golden figures differ.
"""

import argparse
import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from app.agents.router import load_env
from app.agents.schemas import InvestigationRequest, InvestigationResponse
from app.data.repository import DataRepository, FixtureRepository
from app.integrations.hmem import HMemEngine
from app.integrations.meterless import MeterlessConfig, MeterlessError, NightshiftClient
from app.integrations.zetaris import IntegrationNotConfigured
from app.services.agent_investigation import investigate


def show(report: InvestigationResponse) -> None:
    print(f"\n== {report.investigation_id}: {report.incident.supplier_id} +{report.incident.delay_days} days -> {report.status}")
    if report.memory:
        recalled = ", ".join(f"{m.memory_id} ({m.relevance})" for m in report.memory.recalled) or "none"
        print(f"  H-MEM recall: {recalled}")
    print("  plan: " + "; ".join(f"{s.task_id} {s.tool} [{s.origin}]" for s in report.plan))
    for note in report.plan_notes:
        print(f"  plan note: {note}")
    for call in report.tool_calls:
        print(f"  {call.call_id} {call.task_id:<5} {call.tool:<26} {call.status:<9} {call.summary[:90]}")
    for attempt in report.validation.attempts:
        claimed = (f"claimed {attempt.claim.recommended_strategy}, exposure {attempt.claim.penalty_exposure_gbp}, "
                   f"cost {attempt.claim.recommended_total_cost_gbp}" if attempt.claim else "no parseable claim")
        print(f"  attempt {attempt.attempt}: {attempt.outcome} {attempt.failed_checks or ''} ({claimed})")
    print(f"  exposure GBP {report.estimated_penalty_exposure_gbp:.2f}; calculated {report.calculated_recommendation}; "
          f"agent {report.recommended_strategy} at GBP {report.recommended_total_cost_gbp}")
    print(f"  explanation: {report.explanation or '-'}")
    print(f"  evidence: {report.supporting_evidence_ids}")
    for item in report.validation.unresolved:
        print(f"  UNRESOLVED {item}")
    usage = report.model
    print(f"  Nightshift: requested {usage.requested_model} -> {usage.models_used} via {usage.providers}; "
          f"{usage.calls} calls, {usage.signed_receipts} signed receipts {usage.receipt_ids}")
    if report.memory:
        print(f"  H-MEM stored {report.memory.stored_memory_id}; feedback {report.memory.feedback}; "
              f"conflicts {[(c.memory_a, c.memory_b, c.reason) for c in report.memory.conflicts]}; ledger {report.memory.ledger}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, help="write both full JSON reports here")
    parser.add_argument("--memory-dir", type=Path, help="persistent H-MEM directory (default: fresh temp dir)")
    parser.add_argument("--zetaris", action="store_true", help="use Developer 1's ZetarisRepository (needs PR #5)")
    args = parser.parse_args()
    load_env()
    repository: DataRepository = FixtureRepository()
    try:
        if args.zetaris:
            from app.data.zetaris_repository import ZetarisRepository  # available once PR #5 is merged
            from scripts.zetaris_smoke import load_env as load_zetaris_env
            load_zetaris_env()
            repository = ZetarisRepository.from_env()
        config = MeterlessConfig.from_env()
    except (IntegrationNotConfigured, ImportError) as exc:
        print(f"NOT CONFIGURED: {exc}")
        return 2

    with tempfile.TemporaryDirectory(prefix="hmem-") as scratch, NightshiftClient(config) as client:
        memory_dir = args.memory_dir or Path(scratch)
        try:
            models = client.models()
            print(f"Nightshift {config.base_url}: {len(models)} routing ids; requested {config.model} "
                  f"({'listed' if config.model in models else 'NOT LISTED'})")
            reports = []
            with HMemEngine(memory_dir) as memory:
                print(f"H-MEM engine: {memory.version_info} at {memory_dir}")
                for delay in (5, 6):
                    report = investigate(InvestigationRequest(supplier_id="SUP-ALPHA", delay_days=delay), repository,
                                         client, requested_model=config.model, memory=memory)
                    show(report)
                    reports.append(report)
        except MeterlessError as exc:
            print(f"FAILED ({type(exc).__name__}): {exc}")
            return 1
    if args.out:
        args.out.write_text(json.dumps([r.model_dump(mode="json") for r in reports], indent=2), encoding="utf-8")
        print(f"\nfull reports: {args.out}")

    golden, related = reports
    problems = []
    if golden.estimated_penalty_exposure_gbp != Decimal("500.00") or golden.calculated_recommendation != "expedite_shipping":
        problems.append("golden figures changed")
    if not all(r.status == "validated" for r in reports):
        problems.append("an investigation did not validate")
    if related.memory is None or golden.memory.stored_memory_id not in {m.memory_id for m in related.memory.recalled}:
        problems.append("second investigation did not recall the first through H-MEM")
    print("\nRESULT: " + ("PASS" if not problems else "FAIL: " + "; ".join(problems)))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
