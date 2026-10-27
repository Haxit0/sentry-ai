import json
import threading
import time
from decimal import Decimal

import pytest
from app.data.repository import FixtureRepository
from app.integrations.hmem import HMemEngine
from app.integrations.meterless import Completion
from app.v2.data import acquire
from app.v2.decisions import DecisionRequest, compare, counterfactuals, uncertainty
from app.v2.runs import RunStore, sanitize, markdown_packet
from app.v2.workflow import run_investigation, RunStopped

@pytest.fixture
def snapshot(monkeypatch):
    monkeypatch.setenv("SENTRY_DATA_MODE","fixture")
    return acquire("alpha-delay",FixtureRepository())

def test_golden_decision_and_exact_constraints(snapshot):
    req=DecisionRequest(supplier_id="SUP-ALPHA",delay_days=5)
    result=compare(req,snapshot)
    assert result["recommendation"]=="expedite_shipping"
    assert result["simulation"]["estimated_penalty_exposure_gbp"]=="500.00"
    assert next(p for p in result["options"] if p["strategy"]=="expedite_shipping")["total_estimated_cost_gbp"]=="160.00"
    assert compare(req.model_copy(update={"max_action_cost_gbp":Decimal("50.00"),"max_late_days":0}),snapshot)["recommendation"] is None
    assert compare(req.model_copy(update={"max_action_cost_gbp":Decimal("0.00")}),snapshot)["recommendation"]=="accept_delay"

def test_counterfactuals_are_pinned_and_change_strategy(snapshot):
    req=DecisionRequest(supplier_id="SUP-ALPHA",delay_days=5)
    result=counterfactuals(req,snapshot)
    assert len(result["points"])==31
    assert result["points"][0]["strategy"]=="accept_delay"
    assert result["points"][30]["strategy"]=="alternative_supplier"
    assert result["first_change_after_selected_delay"]["delay_days"]==7
    assert result["provenance"]["snapshot_hash"]==snapshot.provenance["snapshot_hash"]

def test_conflicting_and_stale_updates_block_recommendations():
    for case in ("conflicting-eta","stale-update"):
        snap=acquire(case,FixtureRepository())
        result=uncertainty(DecisionRequest(supplier_id="SUP-ALPHA",delay_days=5,case_id=case),snap)
        assert result["blocks_recommendation"]
        assert result["human_question"]
    conflict=uncertainty(DecisionRequest(supplier_id="SUP-ALPHA",delay_days=5),acquire("conflicting-eta",FixtureRepository()))
    assert conflict["reported_delay_range"]==[3,5]

def test_content_hash_stable_despite_new_acquisition_time(snapshot):
    other=acquire("alpha-delay",FixtureRepository())
    assert snapshot.provenance["snapshot_hash"]==other.provenance["snapshot_hash"]
    assert snapshot.provenance["synthetic"]


def test_history_comparison_preserves_snapshots_and_exact_pennies():
    from app.v2.runs import compare_packets
    def packet(rid,cost,hash):
        return {"id":rid,"status":"validated","request":{"delay_days":5},"report":{"recommended_strategy":"expedite_shipping","decision":{"options":[{"strategy":"expedite_shipping","total_estimated_cost_gbp":cost}]},"provenance":{"snapshot_hash":hash}}}
    result=compare_packets(packet("new","160.01","a"),packet("old","160.00","b"))
    assert result["cost_difference_gbp"]=="0.01" and result["snapshot_changed"]
    assert not result["recommendation_changed"]
    assert compare_packets({"id":"failed","status":"failed","request":{}},packet("old","160.00","b"))["cost_difference_gbp"] is None

class ScriptedProvider:
    def __init__(self):self.prompts=[]
    def chat(self,messages,**kwargs):
        system=messages[0]["content"]
        self.prompts.append(system)
        if "Planner" in system:
            payload={"tasks":[{"question":"Read source updates","tool":"get_supply_updates"},{"question":"Test alternatives","tool":"get_counterfactuals"}]} if len(self.prompts)>1 else {"tasks":[]}
        elif "Critic" in system:
            payload={"supported":True,"issues":[],"missing_tools":[]}
        else:
            payload={"recommended_strategy":"expedite_shipping","affected_order_ids":["ORD-1002"],"penalty_exposure_gbp":"500.00","recommended_total_cost_gbp":"160.00","evidence_ids":["supplier:SUP-ALPHA","inventory:SKU-SENSOR","order:ORD-1002","recovery:SUP-ALPHA"],"explanation":"Expedite shipping costs GBP 160.00 against exposure GBP 500.00 for ORD-1002.","assumptions":["Synthetic records"]}
        return Completion(text=json.dumps(payload),model_id="scripted-test",receipt_id="test",receipt_signed=False)

def test_feedback_returns_to_planner_and_memory_is_real(tmp_path):
    provider=ScriptedProvider()
    events=[]
    with HMemEngine(tmp_path/"memory") as engine:
        report=run_investigation(DecisionRequest(supplier_id="SUP-ALPHA",delay_days=5),source=FixtureRepository(),provider=provider,memory=engine,event=lambda a,m:events.append((a,m)))
        assert report["status"]=="validated",report["validation"]
        assert any(agent=="feedback" for agent,_ in events)
        assert sum("Planner" in prompt for prompt in provider.prompts)==2
        assert report["memory"]["stored_memory_id"]
        assert report["memory"]["current_snapshot_hash"]==report["provenance"]["snapshot_hash"]
        hits=engine.query(report["memory"]["query"],top_n=1,threshold=0.45)["memories"]
        assert hits, "Full provenance must not dilute retrieval of the investigation"
        assert any('"scenario_inputs"' in ref and '"source_provenance"' in ref for ref in hits[0]["memory"]["provenance"]["refs"])

def test_contradiction_never_writes_a_validated_memory(tmp_path):
    with HMemEngine(tmp_path/"memory") as engine:
        report=run_investigation(DecisionRequest(supplier_id="SUP-ALPHA",delay_days=5,case_id="conflicting-eta"),source=FixtureRepository(),provider=ScriptedProvider(),memory=engine)
        assert report["status"]=="unresolved"
        assert report["recommended_strategy"] is None
        assert report["memory"]["stored_memory_id"] is None

def test_cancellation_before_work_prevents_memory(tmp_path):
    with HMemEngine(tmp_path/"memory") as engine:
        with pytest.raises(RunStopped):
            run_investigation(DecisionRequest(supplier_id="SUP-ALPHA",delay_days=5),source=FixtureRepository(),provider=ScriptedProvider(),memory=engine,cancelled=lambda:True)
        assert engine.stats()["ledger"].get("create",0)==0

def test_queue_limit_and_cancellation(tmp_path):
    gate=threading.Event()
    def runner(req,event,cancelled):
        gate.wait(5)
        return {"status":"validated"}
    store=RunStore(tmp_path/"runs.db",runner)
    req=DecisionRequest(supplier_id="SUP-ALPHA",delay_days=5)
    try:
        first=store.submit(req);second=store.submit(req);third=store.submit(req)
        with pytest.raises(OverflowError):store.submit(req)
        store.cancel(second["id"])
        gate.set()
        store.executor.shutdown(wait=True)
        assert store.get(second["id"])["status"]=="cancelled"
        assert len(store.history())==3
        assert store.review(first["id"],"approve","operator review")["review"][0]["effect"].startswith("Review record only")
    finally:gate.set()

def test_export_redacts_credentials():
    assert "nvapi-" not in json.dumps(sanitize({"text":"nvapi-abcdefghijklmnopqrst"}))
    assert "secret-token" not in str(sanitize("Bearer secret-token"))
    assert sanitize({"nested":{"password":"a private value"}})["nested"]["password"]=="[REDACTED]"

def test_live_mode_never_falls_back(monkeypatch):
    from app.v2 import data
    monkeypatch.setenv("SENTRY_DATA_MODE","zetaris")
    monkeypatch.setattr(data,"repository",lambda: (_ for _ in ()).throw(RuntimeError("source unavailable")))
    with pytest.raises(RuntimeError,match="source unavailable"):data.acquire()
