"""Explicit data selection and acquisition provenance; never fall back on a live failure."""
import hashlib
import json
import os
from dataclasses import replace
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.data.repository import FixtureRepository
from app.data.zetaris_repository import ZetarisRepository
from app.integrations.zetaris import ZetarisClient, ZetarisConfig

ROOT = Path(__file__).resolve().parents[3]
UPDATE_COLUMNS = ("update_id", "case_id", "supplier_id", "source", "observed_at_utc", "reported_arrival", "freshness_hours", "description")

def now():
    return datetime.now(timezone.utc).isoformat()

def load_settings():
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip().startswith(("SENTRY_", "ZETARIS_", "METERLESS_")):
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

def mode():
    load_settings()
    value = os.environ.get("SENTRY_DATA_MODE", "fixture")
    if value not in ("fixture", "zetaris"):
        raise ValueError("SENTRY_DATA_MODE must be fixture or zetaris")
    return value

def repository():
    if mode() == "fixture":
        return FixtureRepository()
    config = replace(ZetarisConfig.from_env(), read_timeout=20)
    return ZetarisRepository(config)

class Snapshot:
    def __init__(self, source, data, updates, provenance):
        self.source, self.data, self.updates, self.provenance = source, data, updates, provenance

    def snapshot(self):
        return self.data.model_copy(deep=True)

    def evidence_source(self, collection, record_id):
        return self.source.evidence_source(collection, record_id)

def acquire(case_id="alpha-delay", source=None):
    started = now()
    source = source or repository()
    data = source.snapshot()
    queries = [asdict(q) for q in getattr(source, "last_queries", ())]
    is_live = isinstance(source, ZetarisRepository)
    if is_live:
        with ZetarisClient(replace(ZetarisConfig.from_env(), read_timeout=20)) as client:
            result = client.select(("SENTRY_LOGISTICS_PORTAL", "status_updates"), UPDATE_COLUMNS, ("update_id",))
        updates = list(result.rows)
        queries.append({"query_id": result.query_id, "sources": ["SENTRY_LOGISTICS_PORTAL.status_updates"], "rows": len(updates), "time_used_ms": result.time_used_ms})
    else:
        updates = json.loads((ROOT / "backend" / "app" / "data" / "supply_updates.json").read_text(encoding="utf-8"))
    updates = [u for u in updates if u["case_id"] == case_id]
    canonical = json.dumps({"data": data.model_dump(mode="json"), "updates": updates}, sort_keys=True, separators=(",", ":"))
    provenance = {"snapshot_hash": hashlib.sha256(canonical.encode()).hexdigest(), "acquired_from": started,
                  "acquired_until": now(), "data_source": "zetaris" if is_live else "fixture", "synthetic": True,
                  "queries": queries, "as_of_date": str(data.as_of_date),
                  "consistency": "Acquired over an interval; no cross-source atomicity is claimed."}
    return Snapshot(source, data, updates, provenance)
