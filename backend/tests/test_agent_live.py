"""Opt-in live run: real Nightshift inference and the real Meterless H-MEM engine.

    AGENT_LIVE_TESTS=1 python -m pytest tests/test_agent_live.py -v -s

Reads METERLESS_* from the environment or the repository-root .env. Skipped otherwise, so CI
and ordinary runs stay offline. A small local model may need its retries; the assertions only
accept a validated report whose figures equal the deterministic simulator.
"""

import os
from decimal import Decimal

import pytest

from app.agents.router import load_env
from app.agents.schemas import InvestigationRequest
from app.data.repository import FixtureRepository
from app.integrations.hmem import HMemEngine
from app.integrations.meterless import MeterlessConfig, NightshiftClient
from app.services.agent_investigation import investigate

pytestmark = pytest.mark.skipif(os.environ.get("AGENT_LIVE_TESTS") != "1", reason="set AGENT_LIVE_TESTS=1 to call Nightshift")


def test_live_nightshift_discovery_and_completion() -> None:
    load_env()
    config = MeterlessConfig.from_env()
    with NightshiftClient(config) as client:
        assert config.model in client.models()
        completion = client.chat([{"role": "user", "content": "Reply with exactly: PONG"}], max_tokens=16)
    print(f"\n{config.model} -> {completion.model_id} via {completion.provider}; receipt {completion.receipt_id}")
    assert "PONG" in completion.text.upper()
    assert completion.receipt_id and completion.receipt_signed and completion.model_id


def test_live_investigation_validates_and_uses_hmem(tmp_path) -> None:
    load_env()
    config = MeterlessConfig.from_env()
    with NightshiftClient(config) as client, HMemEngine(tmp_path) as memory:
        first = investigate(InvestigationRequest(supplier_id="SUP-ALPHA", delay_days=5), FixtureRepository(), client,
                            requested_model=config.model, memory=memory)
        second = investigate(InvestigationRequest(supplier_id="SUP-ALPHA", delay_days=6), FixtureRepository(), client,
                             requested_model=config.model, memory=memory)
    for report in (first, second):
        print(f"\n{report.investigation_id} +{report.incident.delay_days}: {report.status} after "
              f"{report.validation.attempts_used} attempts; {report.model.models_used}; receipts {report.model.receipt_ids}")
        assert report.status == "validated"
        assert report.recommended_strategy == report.calculated_recommendation
        assert report.model.signed_receipts == report.model.calls > 0
    assert first.estimated_penalty_exposure_gbp == Decimal("500.00") and first.recommended_total_cost_gbp == Decimal("160.00")
    assert first.memory.stored_memory_id in {m.memory_id for m in second.memory.recalled}
    assert second.memory.ledger["read"] >= 1 and second.memory.ledger["feedback"] >= 1
