"""Real provider evaluation. Output is local evidence, never fabricated CI success."""
import argparse
import json
import statistics
import time
from pathlib import Path

from app.integrations.hmem import HMemEngine
from app.integrations.meterless import NightshiftClient, MeterlessConfig
from app.v2.data import ROOT, load_settings, mode
from app.v2.decisions import CASES, DecisionRequest
from app.v2.workflow import run_investigation

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--label",required=True)
    parser.add_argument("--model",default="meterless/local")
    args=parser.parse_args()
    if not args.label.replace("-","").isalnum():
        raise ValueError("Use a simple benchmark label")
    load_settings()
    output=ROOT/"local_data"/"evaluation"/args.label
    if output.exists():
        raise RuntimeError("Use a new label for an independent evaluation")
    output.mkdir(parents=True)
    from dataclasses import replace
    config=replace(MeterlessConfig.from_env(),model=args.model,max_retries=0,read_timeout=30)
    results=[]
    # A final repeated case measures warm memory on the same case after the cold run.
    cases=CASES+[CASES[0]]
    with NightshiftClient(config) as provider,HMemEngine(output/"hmem") as memory:
        for i,case in enumerate(cases):
            inputs={k:v for k,v in case.items() if k!="name"}
            started=time.monotonic()
            try:
                report=run_investigation(DecisionRequest(**inputs),provider=provider,memory=memory,model_id=config.model)
                expected="unresolved" if case["case_id"] in ("conflicting-eta","stale-update","budget-blocked") else "validated"
                result={"case_id":case["case_id"],"repeat":i==len(cases)-1,"status":report["status"],"expected_status":expected,"expected_behavior_passed":report["status"]==expected,
                        "seconds":round(time.monotonic()-started,3),"calls":report.get("model",{}).get("calls",0) if report.get("model") else 0,
                        "attempts":len(report["attempts"]),"tool_calls":len(report["tool_calls"]),"memory_recalled":len((report.get("memory") or {}).get("recalled",[])),
                        "models_used":(report.get("model") or {}).get("models_used",[]),"snapshot_hash":report["provenance"]["snapshot_hash"]}
                (output/f"{i:02}-{case['case_id']}.json").write_text(json.dumps(report,indent=2),encoding="utf8")
            except Exception as exc:
                result={"case_id":case["case_id"],"status":"failed","expected_behavior_passed":False,"seconds":round(time.monotonic()-started,3),"error":f"{type(exc).__name__}: {exc}"}
            results.append(result)
            print(json.dumps(result),flush=True)
            (output/"results.json").write_text(json.dumps(results,indent=2),encoding="utf8")
    summary={"label":args.label,"data_mode":mode(),"requested_model":args.model,"cases":len(results),"expected_behavior_passed":sum(r["expected_behavior_passed"] for r in results),
             "validated":sum(r["status"]=="validated" for r in results),"median_seconds":statistics.median(r["seconds"] for r in results),"results":results}
    (output/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf8")
    print("SUMMARY "+json.dumps({k:v for k,v in summary.items() if k!="results"}),flush=True)

if __name__=="__main__":main()
