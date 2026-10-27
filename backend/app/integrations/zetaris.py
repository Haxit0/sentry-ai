"""Authenticated, bounded, read-only Zetaris adapter.

Transport only: SQL in, string cells out. `app/data/zetaris_repository.py` maps rows to the
shared Pydantic types. Nothing here falls back to fixture data; every failure raises.

Verified against the local Zetaris platform (API 2.4.3.1):
    POST {ZETARIS_BASE_URL}/sql-editor/sqls/run
    Authorization: Bearer <API key>, X-Org-ID: <org>, X-Request-ID: <fresh UUID>
    {"queryId": "<UUID>", "sql": "...", "source": "Generic", "limit": n}
    -> 200 {"headers": [...], "data": [[cell, ...], ...], "total": n, "timeUsed": ms}
Errors arrive as JSON {"msg": "..."} or plain text.
"""

import os
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx


class IntegrationNotConfigured(RuntimeError):
    """Raised rather than inventing successful integration output."""


class ZetarisError(RuntimeError):
    """A configured Zetaris call failed. Never a reason to substitute fixture data."""


class ZetarisUnavailable(ZetarisError):
    """Connection refused, timed out, or the platform answered 5xx."""


class ZetarisAuthError(ZetarisError):
    """The API key or organisation was rejected (401/403)."""


class ZetarisQueryError(ZetarisError):
    """Zetaris rejected the SQL, or answered with an unexpected response shape."""


class ZetarisDataError(ZetarisError):
    """The query succeeded but records are missing, malformed or inconsistent."""


@dataclass(frozen=True)
class IntegrationStatus:
    status: str = "not_configured"
    reason: str = "Set ZETARIS_BASE_URL, ZETARIS_API_TOKEN and ZETARIS_ORG_ID to enable Zetaris mode."


IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
DEFAULT_MAX_ROWS = 1000


def identifier(name: str) -> str:
    """Return `name` if it is a plain SQL identifier; identifiers cannot be bound as parameters."""
    if not isinstance(name, str) or not IDENTIFIER.fullmatch(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


@dataclass(frozen=True)
class ZetarisConfig:
    base_url: str
    api_token: str = field(repr=False)
    org_id: str
    connect_timeout: float = 5.0
    read_timeout: float = 60.0
    max_rows: int = DEFAULT_MAX_ROWS

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ZetarisConfig":
        env = os.environ if environ is None else environ
        values = {key: env.get(key, "").strip() for key in ("ZETARIS_BASE_URL", "ZETARIS_API_TOKEN", "ZETARIS_ORG_ID")}
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise IntegrationNotConfigured(f"Zetaris mode needs {', '.join(missing)}")
        if not values["ZETARIS_ORG_ID"].isdigit():
            raise IntegrationNotConfigured("ZETARIS_ORG_ID must be the numeric organisation id")
        return cls(
            base_url=values["ZETARIS_BASE_URL"].rstrip("/"),
            api_token=values["ZETARIS_API_TOKEN"],
            org_id=values["ZETARIS_ORG_ID"],
            connect_timeout=float(env.get("ZETARIS_CONNECT_TIMEOUT_SECONDS") or 5),
            read_timeout=float(env.get("ZETARIS_READ_TIMEOUT_SECONDS") or 60),
        )


@dataclass(frozen=True)
class QueryResult:
    query_id: str
    sql: str
    headers: tuple[str, ...]
    rows: tuple[dict[str, str | None], ...]
    time_used_ms: int | None


_READ_ONLY = re.compile(r"\s*select\s", re.IGNORECASE)
# Statement keywords that must never reach the read-only path, even nested inside a SELECT.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|create|alter|truncate|grant|revoke|register|refresh|cache|uncache|set|use)\b",
    re.IGNORECASE,
)


class ZetarisClient:
    def __init__(self, config: ZetarisConfig, transport: httpx.BaseTransport | None = None) -> None:
        self._config = config
        self._http = httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.read_timeout, connect=config.connect_timeout),
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ZetarisClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def select(self, table: tuple[str, str], columns: Sequence[str], order_by: Sequence[str]) -> QueryResult:
        """Bounded SELECT over allowlisted identifiers. No caller value is interpolated."""
        source, name = (identifier(part) for part in table)
        cols = ", ".join(identifier(column) for column in columns)
        order = ", ".join(identifier(column) for column in order_by)
        return self.query(f"SELECT {cols} FROM {source}.{name} ORDER BY {order}")

    def query(self, sql: str) -> QueryResult:
        """Run one read-only statement. Results larger than max_rows are refused, not truncated."""
        if not _READ_ONLY.match(sql) or ";" in sql or _FORBIDDEN.search(sql):
            raise ValueError("Only single read-only SELECT statements are allowed")
        result = self._run(sql, self._config.max_rows + 1)
        if len(result.rows) > self._config.max_rows:
            raise ZetarisDataError(f"Query returned more than {self._config.max_rows} rows; refusing partial data")
        return result

    def execute_admin(self, sql: str) -> QueryResult:
        """Unchecked statement, for the explicit dataset registration script only."""
        return self._run(sql, 1)

    def _run(self, sql: str, limit: int) -> QueryResult:
        query_id = str(uuid.uuid4())
        headers = {
            "Authorization": f"Bearer {self._config.api_token}",
            "X-Org-ID": self._config.org_id,
            "X-Request-ID": str(uuid.uuid4()),
        }
        body = {"queryId": query_id, "sql": sql, "source": "Generic", "limit": limit}
        try:
            response = self._http.post("/sql-editor/sqls/run", headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise ZetarisUnavailable(f"Zetaris timed out ({type(exc).__name__})") from exc
        except httpx.TransportError as exc:
            raise ZetarisUnavailable(f"Zetaris unreachable at {self._config.base_url} ({type(exc).__name__})") from exc
        # Zetaris 2.4 answers a wrong API key or organisation with 400 "Not Allowed", not 401.
        if response.status_code in (401, 403) or (response.status_code == 400 and _message(response) == "Not Allowed"):
            raise ZetarisAuthError(f"Zetaris rejected the API key or organisation (HTTP {response.status_code})")
        if response.status_code >= 500:
            raise ZetarisUnavailable(f"Zetaris error HTTP {response.status_code}: {_message(response)}")
        if response.status_code != 200:
            raise ZetarisQueryError(f"Zetaris rejected the query (HTTP {response.status_code}): {_message(response)}")
        return _parse(response, query_id, sql)


def _message(response: httpx.Response) -> str:
    try:
        payload = response.json()
        text = payload.get("msg") if isinstance(payload, dict) else None
    except ValueError:
        text = None
    text = text or response.text
    # Zetaris embeds Java stack traces in messages; keep the meaningful head.
    return text.strip().split("\n\tat ")[0][:300]


def _parse(response: httpx.Response, query_id: str, sql: str) -> QueryResult:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ZetarisQueryError("Zetaris returned a non-JSON success response") from exc
    headers, data = (payload.get("headers"), payload.get("data")) if isinstance(payload, dict) else (None, None)
    if not isinstance(headers, list) or not all(isinstance(h, str) for h in headers) or not isinstance(data, list):
        raise ZetarisQueryError("Unexpected Zetaris response shape: expected headers[] and data[][]")
    if len(set(headers)) != len(headers):
        raise ZetarisQueryError("Zetaris response has duplicate column names")
    rows = []
    for index, row in enumerate(data):
        if not isinstance(row, list) or len(row) != len(headers) or not all(c is None or isinstance(c, str) for c in row):
            raise ZetarisQueryError(f"Malformed Zetaris row {index}: expected {len(headers)} string cells")
        rows.append(dict(zip(headers, row)))
    time_used = payload.get("timeUsed")
    return QueryResult(query_id, sql, tuple(headers), tuple(rows), time_used if isinstance(time_used, int) else None)


def __getattr__(name: str) -> Any:
    # Kept importable from here for existing callers; it lives in the data layer, which imports this module.
    if name == "ZetarisRepository":
        from app.data.zetaris_repository import ZetarisRepository
        return ZetarisRepository
    raise AttributeError(name)
