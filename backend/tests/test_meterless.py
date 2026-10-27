"""Nightshift client (mocked transport) and the real Meterless H-MEM engine.

Nightshift tests use httpx.MockTransport and never touch the network. H-MEM tests run the
vendored engine in Node and skip only when Node 22.7+ is unavailable. Live Nightshift checks
are in `scripts/agent_smoke.py` and `tests/test_agent_live.py`.
"""

import json
import shutil
import subprocess

import httpx
import pytest

from app.integrations.hmem import EngineCallError, EngineUnavailable, HMemEngine
from app.integrations.meterless import (
    MeterlessAuthError, MeterlessClient, MeterlessConfig, MeterlessResponseError, MeterlessUnavailable,
    NightshiftClient, parse_completion,
)
from app.integrations.zetaris import IntegrationNotConfigured

TOKEN = "test-proxy-token-not-real"
CONFIG = MeterlessConfig(base_url="http://nightshift.test/v1", api_token=TOKEN, model="meterless/local", max_retries=2)
CLOCK = 1_793_000_000_000

# Shape recorded from Nightshift 1.2.1 (receipt envelope shortened).
COMPLETION = {
    "id": "chatcmpl-1", "object": "chat.completion", "model": "local-runtime/qwen2.5-coder-3b-instruct",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": '```json\n{"tasks": []}\n```'}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 93, "completion_tokens": 35, "total_tokens": 128},
    "meterless_cross_check": {"status": "passed"},
    "meterless": {
        "requested_model": "meterless/local", "routed_model": "local-runtime/qwen2.5-coder-3b-instruct",
        "winning_route": {"model": "local-runtime/qwen2.5-coder-3b-instruct", "provider": "local-runtime", "kind": "local"},
        "receipt_id": "rcpt_req_test", "receipt_envelope": {"sig_b64": "..."}, "usage": {"latency_ms": 5509},
    },
}


def client(handler, sleeps: list[float] | None = None) -> NightshiftClient:
    return NightshiftClient(CONFIG, transport=httpx.MockTransport(handler), sleep=(sleeps if sleeps is not None else []).append)


def node_runs_hmem() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    return subprocess.run([node, "--experimental-transform-types", "--no-warnings", "-e", "0"], capture_output=True).returncode == 0


needs_node = pytest.mark.skipif(not node_runs_hmem(), reason="H-MEM engine needs Node 22.7+ on PATH")


def test_completion_parsing_keeps_routing_and_receipt_metadata() -> None:
    completion = parse_completion(COMPLETION, "meterless/local")
    assert completion.text.startswith("```json")
    assert completion.model_id == "local-runtime/qwen2.5-coder-3b-instruct"
    assert (completion.provider, completion.receipt_id, completion.receipt_signed) == ("local-runtime", "rcpt_req_test", True)
    assert (completion.prompt_tokens, completion.completion_tokens, completion.latency_ms) == (93, 35, 5509)
    assert completion.cross_check == "passed" and completion.requested_model == "meterless/local"


def test_chat_sends_bearer_token_app_header_and_routing_id() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=COMPLETION)

    with client(handler) as nightshift:
        nightshift.chat([{"role": "user", "content": "hi"}], max_tokens=20)
    request = seen[0]
    assert request.url == "http://nightshift.test/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert request.headers["meterless-app"] == "sentry-ai"
    body = json.loads(request.content)
    assert body["model"] == "meterless/local" and body["stream"] is False and body["max_tokens"] == 20


def test_model_discovery_lists_routing_ids() -> None:
    with client(lambda r: httpx.Response(200, json={"data": [{"id": "meterless/local"}, {"id": "meterless/auto"}, {"x": 1}]})) as nightshift:
        assert nightshift.models() == ["meterless/local", "meterless/auto"]


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_token_raises_auth_error_without_retry_or_leak(status: int) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "invalid token"}})

    with client(handler) as nightshift, pytest.raises(MeterlessAuthError) as caught:
        nightshift.chat([{"role": "user", "content": "hi"}])
    assert len(calls) == 1 and TOKEN not in str(caught.value)


def test_unreachable_runtime_raises_unavailable_after_bounded_retries() -> None:
    calls, sleeps = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("refused", request=request)

    with client(handler, sleeps) as nightshift, pytest.raises(MeterlessUnavailable, match="after 3 attempts"):
        nightshift.chat([{"role": "user", "content": "hi"}])
    assert len(calls) == 3 and len(sleeps) == 2


def test_not_ready_runtime_is_retried_then_succeeds() -> None:
    responses = [httpx.Response(503, json={"error": {"message": "The local runtime is not ready."}}), httpx.Response(200, json=COMPLETION)]
    with client(lambda r: responses.pop(0)) as nightshift:
        assert nightshift.chat([{"role": "user", "content": "hi"}]).receipt_id == "rcpt_req_test"


def test_persistent_5xx_raises_unavailable_with_runtime_message() -> None:
    with client(lambda r: httpx.Response(503, json={"error": {"message": "The local runtime is not ready."}})) as nightshift:
        with pytest.raises(MeterlessUnavailable, match="not ready"):
            nightshift.chat([{"role": "user", "content": "hi"}])


def test_client_errors_are_not_retried() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400, json={"error": {"message": "bad model"}})

    with client(handler) as nightshift, pytest.raises(MeterlessResponseError, match="bad model"):
        nightshift.chat([{"role": "user", "content": "hi"}])
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [
    {"choices": []},
    {"choices": [{"message": {"content": "   "}}]},
    {"choices": [{"message": {"content": None}}]},
    {"error": "nope"},
])
def test_unusable_completion_bodies_are_rejected(payload: dict) -> None:
    with client(lambda r: httpx.Response(200, json=payload)) as nightshift, pytest.raises(MeterlessResponseError):
        nightshift.chat([{"role": "user", "content": "hi"}])


def test_configuration_reads_token_file_and_hides_token(tmp_path) -> None:
    token_file = tmp_path / "proxy-token"
    token_file.write_text(TOKEN + "\n", encoding="utf-8")
    config = MeterlessConfig.from_env({"METERLESS_BASE_URL": "http://x/v1/", "METERLESS_TOKEN_FILE": str(token_file)})
    assert (config.base_url, config.api_token, config.model) == ("http://x/v1", TOKEN, "meterless/local")
    assert TOKEN not in repr(config)


@pytest.mark.parametrize("env", [{}, {"METERLESS_BASE_URL": "http://x/v1"}, {"METERLESS_BASE_URL": "http://x/v1", "METERLESS_TOKEN_FILE": "/no/such/file"}])
def test_missing_configuration_is_explicit(env: dict) -> None:
    with pytest.raises(IntegrationNotConfigured):
        MeterlessConfig.from_env(env)


def test_unconfigured_facade_still_refuses_to_fabricate() -> None:
    facade = MeterlessClient()
    assert facade.status().status == "not_configured"
    with pytest.raises(IntegrationNotConfigured):
        facade.complete(prompt="x", model_id="meterless/local")
    configured = MeterlessClient(CONFIG, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=COMPLETION)))
    assert configured.status().nightshift == "configured"
    assert configured.complete(prompt="x", model_id="").receipt_id == "rcpt_req_test"


def test_missing_node_is_reported_as_engine_unavailable() -> None:
    with pytest.raises(EngineUnavailable):
        HMemEngine(node="/definitely/not/node")


@needs_node
def test_hmem_engine_stores_retrieves_and_audits_with_provenance() -> None:
    with HMemEngine(clock_ms=CLOCK) as engine:
        assert engine.version_info == {"engine": "H-MEM", "package": "@meterless/hmem-reference", "version": "0.1.0",
                                       "persistent": False, "records": 0}
        stored = engine.add("Supplier disruption SUP-ALPHA Alpha Components SKU-SENSOR delayed 5 days. Validated expedite_shipping.",
                            source="sentry-ai://investigations/inv-1", tags=["supplier:SUP-ALPHA", "strategy:expedite_shipping"],
                            confidence=0.9, layer="long_term", refs=["order:ORD-1002"])
        assert stored["id"] == "mem-1" and stored["source"] == "sentry-ai://investigations/inv-1"
        assert stored["provenance"] == {"origin": "plan_completion", "label": "sentry-ai://investigations/inv-1",
                                        "refs": ["order:ORD-1002"], "learnedAt": CLOCK}
        hits = engine.query("Supplier disruption SUP-ALPHA Alpha Components SKU-SENSOR delayed 6 days", threshold=0.45)
        assert [h["memory"]["id"] for h in hits["memories"]] == ["mem-1"]
        assert "[MEMORY CONTEXT]" in hits["context"] and "<mem-1>" in hits["context"]
        other = engine.query("Supplier disruption SUP-GAMMA Gamma Electronics SKU-CONTROL delayed 5 days", threshold=0.45)
        assert other["memories"] == []
        after = engine.feedback("mem-1", "wrong")
        assert after["confidence"] == pytest.approx(0.7) and "review" in after["tags"]
        assert [entry["action"] for entry in engine.history("mem-1")] == ["create", "read", "feedback"]
        assert engine.stats() == {"records": 1, "ledger": {"create": 1, "read": 1, "feedback": 1}}


@needs_node
def test_hmem_rejects_records_without_source() -> None:
    with HMemEngine(clock_ms=CLOCK) as engine, pytest.raises(EngineCallError, match="no source"):
        engine.add("Unsourced claim", source="")


@needs_node
def test_hmem_flags_conflicting_figures_for_the_same_situation() -> None:
    with HMemEngine(clock_ms=CLOCK) as engine:
        engine.add("Supplier disruption SUP-ALPHA delayed 5 days. Exposure GBP 500.00; expedite total GBP 160.00.", source="a")
        engine.add("Supplier disruption SUP-ALPHA delayed 5 days. Exposure GBP 500.00; expedite total GBP 190.00.", source="b")
        conflicts = engine.scan_conflicts()
        assert [(c["memoryA"], c["memoryB"], c["reason"]) for c in conflicts] == [("mem-1", "mem-2", "high-similarity conflicting numeric values")]


@needs_node
def test_hmem_persists_between_engine_processes(tmp_path) -> None:
    with HMemEngine(tmp_path, clock_ms=CLOCK) as engine:
        engine.add("Supplier disruption SUP-BETA Beta Packaging SKU-CASING delayed 5 days.", source="s")
    assert (tmp_path / "state.json").exists() and (tmp_path / "ledger.jsonl").exists()
    with HMemEngine(tmp_path, clock_ms=CLOCK) as engine:
        assert engine.version_info["records"] == 1 and engine.version_info["persistent"] is True
        assert engine.stats()["ledger"] == {"create": 1}
