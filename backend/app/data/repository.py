"""Read-only repository boundary; Zetaris data maps to these same types."""

from pathlib import Path
from typing import Protocol

from app.data.validation import validate_snapshot
from app.schemas import DemoData

FIXTURE_SOURCE = "backend/app/data/demo_data.json"


class DataRepository(Protocol):
    def snapshot(self) -> DemoData:
        """Return a validated, isolated snapshot including provenance dates."""
        ...


def evidence_source(repository: object, collection: str, record_id: str) -> str:
    """Provenance label for one record. Repositories without their own labels are fixture-backed."""
    label = getattr(repository, "evidence_source", None)
    return label(collection, record_id) if callable(label) else f"{FIXTURE_SOURCE}#{collection}/{record_id}"


class FixtureRepository:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Path(__file__).with_name("demo_data.json")

    def snapshot(self) -> DemoData:
        return validate_snapshot(DemoData.model_validate_json(self._path.read_text(encoding="utf-8")))

    def evidence_source(self, collection: str, record_id: str) -> str:
        return f"{FIXTURE_SOURCE}#{collection}/{record_id}"
