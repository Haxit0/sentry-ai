"""Live Zetaris smoke test: real queries, validation, and simulation over the result.

Usage, from `backend`:  python -m scripts.zetaris_smoke
Reads ZETARIS_* settings from the environment, else from the repository-root .env.
Prints sources, counts and query timings only: never tokens, headers or customer fields.
Exits non-zero on any failure; it never substitutes fixture data.
"""

import os
import sys
from pathlib import Path

from app.data.zetaris_repository import ZetarisRepository
from app.integrations.zetaris import IntegrationNotConfigured, ZetarisError
from app.schemas import SimulationRequest
from app.services.simulation import simulate

REPO_ENV = Path(__file__).resolve().parents[2] / ".env"


def load_env(path: Path = REPO_ENV) -> None:
    """Set ZETARIS_* keys from a dotenv file without overriding the real environment."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip().startswith("ZETARIS_"):
            os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    load_env()
    try:
        repository = ZetarisRepository.from_env()
        print(f"Zetaris API: {os.environ['ZETARIS_BASE_URL']} (org {os.environ['ZETARIS_ORG_ID']})")
        data = repository.snapshot()
    except IntegrationNotConfigured as exc:
        print(f"NOT CONFIGURED: {exc}")
        return 2
    except ZetarisError as exc:
        print(f"FAILED ({type(exc).__name__}): {exc}")
        return 1
    for query in repository.last_queries:
        print(f"  queried {' JOIN '.join(query.sources):<62} rows={query.rows:<3} "
              f"timeUsed={query.time_used_ms}ms queryId={query.query_id}")
    print(f"validation: passed ({len(data.suppliers)} suppliers, {len(data.orders)} orders, "
          f"{len(data.inventory)} inventory SKUs; as of {data.as_of_date})")

    result = simulate(SimulationRequest(supplier_id="SUP-ALPHA", delay_days=5), repository)
    exposure, best = result.estimated_penalty_exposure_gbp, result.recovery_options[0]
    print(f"simulation SUP-ALPHA +5 days: exposure GBP {exposure:.2f}; "
          f"recommended {result.recommended_strategy} at GBP {best.total_estimated_cost_gbp:.2f}")
    sources = sorted({item.source.split("/")[2] for item in result.evidence})
    print(f"evidence sources: {', '.join(sources)}")
    if any("demo_data.json" in item.source for item in result.evidence):
        print("FAILED: live evidence cites the fixture")
        return 1
    print("simulator consumed Zetaris data: yes")
    # The frozen v1 contract can only say "fixture"; this run is not served through the API.
    print(f"note: response literals are contract-frozen (execution_mode={result.execution_mode!r}, "
          "disclaimer says no Zetaris); see docs/ZETARIS_INTEGRATION.md for the proposed change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
