"""Single-worker, bounded local run queue with durable events and cooperative cancellation."""
import json
import os
import re
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.v2.data import ROOT, now
from app.v2.workflow import RunStopped, run_investigation

TERMINAL = {"validated","unresolved","failed","cancelled"}

def sanitize(value):
    private_fields={"authorization","api_key","apikey","api_token","password","secret","proxy_token","access_token","refresh_token","idtoken","refreshtoken"}
    def scrub(item):
        if isinstance(item,dict):
            return {k:("[REDACTED]" if k.lower() in private_fields else scrub(v)) for k,v in item.items()}
        if isinstance(item,list):
            return [scrub(v) for v in item]
        return item
    text = json.dumps(scrub(value), default=str)
    text = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?:sk-|nvapi-)[A-Za-z0-9_-]{12,}", "[REDACTED]", text)
    return json.loads(text)

class RunStore:
    def __init__(self, path=None, runner=None):
        self.path = Path(path or os.environ.get("SENTRY_RUN_DB") or ROOT/"local_data"/"runs.sqlite3")
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(3)
        self.executor = ThreadPoolExecutor(max_workers=1,thread_name_prefix="sentry-investigation")
        self.runner = runner or run_investigation
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, request TEXT, status TEXT, created_at TEXT, updated_at TEXT, events TEXT, report TEXT, error TEXT, cancelled INTEGER DEFAULT 0, review TEXT)")
            db.execute("UPDATE runs SET status='failed',error='Application restarted before completion',updated_at=? WHERE status IN ('queued','running')",(now(),))

    def connect(self):
        db = sqlite3.connect(self.path,timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def get(self,run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone()
        if not row:
            raise KeyError(run_id)
        value = dict(row)
        for key in ("request","events","report","review"):
            value[key] = json.loads(value[key]) if value[key] else None
        return value

    def history(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT id,status,created_at,updated_at,error FROM runs ORDER BY created_at DESC LIMIT 30")]

    def update(self,run_id,**values):
        permitted={"status","events","report","error","cancelled","review"}
        if not set(values)<=permitted:
            raise ValueError("Unknown run field")
        values["updated_at"] = now()
        with self.lock,self.connect() as db:
            db.execute("UPDATE runs SET "+",".join(f"{k}=?" for k in values)+" WHERE id=?",(*values.values(),run_id))

    def event(self,run_id,agent,message):
        with self.lock:
            value=self.get(run_id)
            events=value["events"] or []
            events.append({"at":now(),"agent":agent,"message":message})
            self.update(run_id,events=json.dumps(sanitize(events)))

    def submit(self,request):
        if not self.slots.acquire(blocking=False):
            raise OverflowError("One investigation is running and two are queued. Try again after a run finishes.")
        run_id="run-"+uuid.uuid4().hex[:12]
        try:
            with self.connect() as db:
                db.execute("INSERT INTO runs(id,request,status,created_at,updated_at,events) VALUES(?,?,?,?,?,?)",(run_id,request.model_dump_json(),"queued",now(),now(),"[]"))
            self.executor.submit(self.execute,run_id,request)
            return self.get(run_id)
        except Exception:
            self.slots.release()
            raise

    def execute(self,run_id,request):
        try:
            if self.get(run_id)["cancelled"]:
                self.update(run_id,status="cancelled")
                return
            self.update(run_id,status="running")
            report=self.runner(request,event=lambda a,m:self.event(run_id,a,m),cancelled=lambda:bool(self.get(run_id)["cancelled"]))
            # A late cancellation never publishes an accepted recommendation.
            with self.lock:
                if self.get(run_id)["cancelled"]:
                    self.update(run_id,status="cancelled")
                else:
                    self.update(run_id,status=report["status"],report=json.dumps(sanitize(report)))
        except RunStopped as exc:
            self.update(run_id,status="cancelled" if self.get(run_id)["cancelled"] else "unresolved",error=str(exc))
        except Exception as exc:
            self.update(run_id,status="failed",error=sanitize(f"{type(exc).__name__}: {exc}")[:500])
        finally:
            self.slots.release()

    def cancel(self,run_id):
        with self.lock:
            value=self.get(run_id)
            if value["status"] not in TERMINAL:
                self.update(run_id,cancelled=1,status="cancelled" if value["status"]=="queued" else value["status"])
                self.event(run_id,"operator","Cancellation requested; active model call may finish before work stops")
            return self.get(run_id)

    def review(self,run_id,action,note):
        with self.lock:
            value=self.get(run_id)
            if value["status"] not in TERMINAL:
                raise ValueError("Wait for the investigation to finish")
            if action=="approve" and value["status"]!="validated":
                raise ValueError("Only a validated recommendation can be approved")
            reviews=value["review"] or []
            reviews.append({"action":action,"note":note,"at":now(),"effect":"Review record only; no purchase or shipment executed"})
            self.update(run_id,review=json.dumps(sanitize(reviews)))
            return self.get(run_id)

def markdown_packet(value):
    report=value.get("report") or {}
    return "\n".join(["# Sentry AI decision packet",f"Run: {value['id']}",f"Status: {value['status']}",
        "Synthetic data. Recommendations only; no external actions executed.","", "## Recommendation",
        str(report.get("recommended_strategy") or "No validated recommendation"),str(report.get("explanation") or value.get("error") or ""),
        "", "## Evidence, validation, assumptions and model metadata", "```json",json.dumps(sanitize(report),indent=2),"```",
        "", "## Execution trace", "```json",json.dumps(value.get("events"),indent=2),"```", "", "## Human reviews",json.dumps(value.get("review"),indent=2)])


def compare_packets(current, previous):
    """Compare recorded calculations, without reacquiring or mixing their snapshots."""
    from decimal import Decimal

    def describe(run):
        report = run.get("report") or {}
        decision = report.get("decision") or {}
        strategy = report.get("recommended_strategy")
        option = next((o for o in decision.get("options", []) if o["strategy"] == strategy), None)
        return {"run_id": run["id"], "status": run["status"], "inputs": run["request"],
                "recommendation": strategy, "total_estimated_cost_gbp": option["total_estimated_cost_gbp"] if option else None,
                "snapshot_hash": report.get("provenance", {}).get("snapshot_hash")}

    left, right = describe(current), describe(previous)
    a, b = left["total_estimated_cost_gbp"], right["total_estimated_cost_gbp"]
    return {"current": left, "previous": right, "recommendation_changed": left["recommendation"] != right["recommendation"],
            "snapshot_changed": left["snapshot_hash"] != right["snapshot_hash"],
            "cost_difference_gbp": f"{Decimal(a)-Decimal(b):.2f}" if a is not None and b is not None else None,
            "limitation": "Recorded scenarios may have different inputs and evidence. A cost difference is not realized savings."}
