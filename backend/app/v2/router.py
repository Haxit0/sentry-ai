"""Versioned API for live data, decisions and durable investigation runs."""
from functools import lru_cache
from typing import Literal
from fastapi import APIRouter, HTTPException, Response
from pydantic import Field

from app.schemas import ContractModel
from app.integrations.zetaris import IntegrationNotConfigured, ZetarisError
from app.integrations.meterless import MeterlessConfig, NightshiftClient
from app.integrations.hmem import HMemEngine, default_state_dir
from app.services.simulation import UnknownSupplierError
from app.v2.data import acquire, mode, load_settings
from app.v2.decisions import DecisionRequest, CASES, compare, counterfactuals, uncertainty
from app.v2.runs import RunStore, markdown_packet, sanitize, compare_packets

router=APIRouter(prefix="/api/v2",tags=["Submission workflow"])

@lru_cache
def store():
    load_settings()
    return RunStore()

def snapshot(case_id="alpha-delay"):
    try:
        return acquire(case_id)
    except (IntegrationNotConfigured,ZetarisError) as exc:
        raise HTTPException(503, f"Data source unavailable: {type(exc).__name__}: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(503,f"Invalid source data/configuration: {exc}") from exc

def get_run(run_id):
    try:
        return store().get(run_id)
    except KeyError:
        raise HTTPException(404,"Unknown investigation run")

@router.get("/status")
def status():
    result={"data_mode":mode(),"synthetic":True,"zetaris":{"status":"not_configured"},"nightshift":{"status":"unavailable"},"hmem":{"status":"unavailable"}}
    try:
        data=snapshot()
        result.update(as_of_date=str(data.data.as_of_date),provenance=data.provenance)
        result["zetaris"]={"status":"connected" if mode()=="zetaris" else "not_configured","reason":"Last acquisition succeeded" if mode()=="zetaris" else "Explicit fixture mode"}
    except HTTPException as exc:
        result["zetaris"]={"status":"unavailable","reason":exc.detail}
    try:
        config=MeterlessConfig.from_env()
        from dataclasses import replace
        with NightshiftClient(replace(config,read_timeout=5,max_retries=0)) as client:
            models=client.models()
        result["nightshift"]={"status":"reachable","requested_model":config.model,"catalogue_models":len(models),"reason":"Discovery succeeded; only a completed investigation proves inference readiness"}
    except Exception as exc:
        result["nightshift"]={"status":"unavailable","reason":str(exc)[:300]}
    try:
        with HMemEngine(default_state_dir() / "submission") as engine:
            result["hmem"]={"status":"connected","implementation":engine.version_info,"persistent":True}
    except Exception as exc:
        result["hmem"]={"status":"unavailable","reason":str(exc)[:300]}
    return sanitize(result)

@router.get("/cases")
def cases():
    return CASES

@router.get("/workspace")
def workspace():
    snap=snapshot()
    return {"suppliers":snap.data.model_dump(mode="json")["suppliers"],"orders":snap.data.model_dump(mode="json")["orders"],"provenance":snap.provenance}

@router.post("/simulations")
def simulation(request:DecisionRequest):
    try:
        snap=snapshot(request.case_id)
        return {**compare(request,snap),"counterfactuals":counterfactuals(request,snap),"uncertainty":uncertainty(request,snap)}
    except UnknownSupplierError as exc:
        raise HTTPException(404,str(exc))

@router.post("/investigation-runs",status_code=202)
def create_run(request:DecisionRequest):
    load_settings()
    try:
        return store().submit(request)
    except OverflowError as exc:
        raise HTTPException(429,str(exc))

@router.get("/investigation-runs")
def history():
    return store().history()

@router.get("/investigation-runs/{run_id}")
def run(run_id:str):
    return get_run(run_id)

@router.post("/investigation-runs/{run_id}/cancel")
def cancel(run_id:str):
    get_run(run_id)
    return store().cancel(run_id)

@router.get("/investigation-runs/{run_id}/comparison")
def comparison(run_id:str,against:str):
    return compare_packets(get_run(run_id),get_run(against))

class Review(ContractModel):
    action:Literal["approve","request_revision","defer"]
    note:str=Field(default="",max_length=1200)

@router.post("/investigation-runs/{run_id}/review")
def review(run_id:str,request:Review):
    get_run(run_id)
    try:
        return store().review(run_id,request.action,request.note)
    except ValueError as exc:
        raise HTTPException(409,str(exc))

@router.get("/investigation-runs/{run_id}/export")
def export(run_id:str,format:Literal["json","markdown"]="json"):
    value=sanitize(get_run(run_id))
    if format=="markdown":
        return Response(markdown_packet(value),media_type="text/markdown",headers={"Content-Disposition":f'attachment; filename="{run_id}.md"'})
    import json
    return Response(json.dumps(value,indent=2),media_type="application/json",headers={"Content-Disposition":f'attachment; filename="{run_id}.json"'})
