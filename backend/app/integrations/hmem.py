"""Meterless H-MEM Engine client.

Runs the vendored, unmodified Meterless H-MEM reference engine (`backend/engines/hmem`) in a
Node child process and talks to it over JSON lines (`backend/engines/hmem_bridge.mjs`). Every
add, query, feedback and conflict scan is executed by the engine's own services and recorded
in its append-only trust ledger. Needs Node 22.7+ for `--experimental-transform-types`.
"""

import json
import os
import shutil
import subprocess
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.integrations.meterless import MeterlessError


class EngineUnavailable(MeterlessError):
    """Node is missing or too old, or the H-MEM bridge process failed."""


class EngineCallError(MeterlessError):
    """The engine rejected a call, for example a record with no source."""


ENGINES_DIR = Path(__file__).resolve().parents[2] / "engines"
BRIDGE = ENGINES_DIR / "hmem_bridge.mjs"
NODE_FLAGS = ("--experimental-transform-types", "--no-warnings")
UPSTREAM_COMMIT = "1742dec56a66e58eef9dda2d2b865823758ca8cd"


def default_state_dir() -> Path:
    return Path(os.environ.get("SENTRY_HMEM_DIR") or Path.home() / ".local" / "state" / "sentry-ai" / "hmem")


class HMemEngine:
    def __init__(
        self, persist_dir: Path | None = None, *, clock_ms: int | None = None,
        node: str | None = None, timeout: float = 10.0,
    ) -> None:
        executable = node or os.environ.get("SENTRY_NODE") or shutil.which("node")
        if not executable:
            raise EngineUnavailable("H-MEM needs Node 22.7+ on PATH (or SENTRY_NODE)")
        command = [executable, *NODE_FLAGS, str(BRIDGE), "--actor", "sentry-ai"]
        if persist_dir is not None:
            command += ["--persist-dir", str(persist_dir)]
        if clock_ms is not None:
            command += ["--clock-ms", str(clock_ms)]
        try:
            self._process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", bufsize=1,
            )
        except OSError as exc:
            raise EngineUnavailable(f"Cannot start the H-MEM bridge ({type(exc).__name__})") from exc
        self._timeout = timeout
        self._lock = threading.Lock()
        self._next_id = 0
        self.persistent = persist_dir is not None
        self.version_info = self.call("info")

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.stdin.close()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        for stream in (self._process.stdout, self._process.stderr):
            if stream:
                stream.close()

    def __enter__(self) -> "HMemEngine":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def call(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
            if self._process.poll() is not None:
                raise EngineUnavailable(f"H-MEM bridge exited: {self._stderr()}")
            try:
                self._process.stdin.write(json.dumps({"id": request_id, "method": method, "params": params or {}}) + "\n")
                self._process.stdin.flush()
            except OSError as exc:
                raise EngineUnavailable(f"H-MEM bridge closed its input: {self._stderr()}") from exc
            line = self._readline()
        try:
            response = json.loads(line)
        except ValueError as exc:
            raise EngineUnavailable(f"H-MEM bridge sent a non-JSON line: {line[:200]!r}") from exc
        if response.get("id") != request_id:
            raise EngineUnavailable("H-MEM bridge response id mismatch")
        if "error" in response:
            raise EngineCallError(f"H-MEM {method} failed: {response['error']}")
        return response.get("result")

    def _readline(self) -> str:
        result: list[str] = []
        reader = threading.Thread(target=lambda: result.append(self._process.stdout.readline()), daemon=True)
        reader.start()
        reader.join(self._timeout)
        if reader.is_alive():
            self._process.kill()
            raise EngineUnavailable(f"H-MEM bridge did not answer within {self._timeout}s")
        if not result or not result[0]:
            raise EngineUnavailable(f"H-MEM bridge exited: {self._stderr()}")
        return result[0]

    def _stderr(self) -> str:
        if self._process.poll() is None or not self._process.stderr:
            return "no diagnostic"
        return (self._process.stderr.read() or "no diagnostic").strip()[-300:]

    # Engine operations (H-MEM reference: store.add, retrieval.query, retrieval.feedback, conflicts.scan).
    def add(
        self, content: str, *, source: str, tags: Sequence[str] = (), confidence: float = 0.7,
        layer: str = "working", memory_type: str = "general", refs: Sequence[str] = (), label: str = "",
    ) -> dict[str, Any]:
        provenance = {"origin": "plan_completion", "label": label or source, "refs": list(refs)}
        return self.call("add", {
            "content": content, "source": source, "tags": list(tags), "confidence": confidence,
            "layer": layer, "type": memory_type, "provenance": provenance,
        })

    def query(self, text: str, *, top_n: int = 3, threshold: float | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"query": text, "topN": top_n}
        if threshold is not None:
            params["threshold"] = threshold
        return self.call("query", params)

    def feedback(self, memory_id: str, kind: str) -> dict[str, Any]:
        return self.call("feedback", {"memoryId": memory_id, "kind": kind})

    def scan_conflicts(self) -> list[dict[str, Any]]:
        return self.call("scan_conflicts")

    def history(self, memory_id: str) -> list[dict[str, Any]]:
        return self.call("history", {"memoryId": memory_id})

    def stats(self) -> dict[str, Any]:
        return self.call("stats")
