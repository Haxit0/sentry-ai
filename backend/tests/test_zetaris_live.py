"""Opt-in live check against a real Zetaris platform seeded by scripts/seed_zetaris_dev.sh.

    ZETARIS_LIVE_TESTS=1 python -m pytest tests/test_zetaris_live.py -v -s

Reads ZETARIS_* from the environment or the repository-root .env. Skipped otherwise, so CI
and ordinary runs stay offline.
"""

import os
from decimal import Decimal

import pytest

from app.data.zetaris_repository import ZetarisRepository
from app.schemas import SimulationRequest
from app.services.simulation import simulate
from scripts.zetaris_smoke import load_env

pytestmark = pytest.mark.skipif(os.environ.get("ZETARIS_LIVE_TESTS") != "1", reason="set ZETARIS_LIVE_TESTS=1 to query Zetaris")


def test_live_snapshot_is_federated_validated_and_simulated() -> None:
    load_env()
    repository = ZetarisRepository.from_env()
    data = repository.snapshot()
    queried = [query.sources for query in repository.last_queries]
    print(f"\nqueried: {queried}; rows: {[q.rows for q in repository.last_queries]}")
    assert ("SENTRY_ERP_PG.customer_orders", "SENTRY_SUPPLIER_PORTAL.suppliers") in queried
    assert (len(data.suppliers), len(data.orders), len(data.inventory)) == (3, 6, 3)

    result = simulate(SimulationRequest(supplier_id="SUP-ALPHA", delay_days=5), repository)
    assert result.estimated_penalty_exposure_gbp == Decimal("500.00")
    assert result.recommended_strategy == "expedite_shipping"
    assert all(item.source.startswith("zetaris://") for item in result.evidence)
