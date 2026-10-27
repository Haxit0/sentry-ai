"""Namespaced local demo setup. Reads credentials privately; never prints them."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import uuid
import httpx

from app.v2.data import ROOT
from app.integrations.zetaris import ZetarisClient, ZetarisConfig, ZetarisQueryError
from scripts.register_zetaris_sources import statements

def env_file(path):
    result={}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        k,s,v=line.partition("=")
        if s and not k.lstrip().startswith("#"):
            result[k.strip()]=v.strip().strip('"').strip("'")
    return result

def main():
    install=Path(os.environ.get("SENTRY_ZETARIS_INSTALL",str(Path.home()/"zetaris-platform")))
    settings=env_file(install/".env")
    username=settings.get("ZETARIS_ADMIN_EMAIL",settings.get("ZETARIS_ADMIN_USERNAME","admin@zetaris.com"))
    password=settings.get("ZETARIS_ADMIN_PASSWORD")
    if not password:
        raise RuntimeError("Saved Zetaris administrator password is absent")
    root_env=ROOT/".env"
    current=env_file(root_env) if root_env.exists() else {}
    if not current.get("ZETARIS_API_TOKEN"):
        with httpx.Client(timeout=30) as http:
            response=http.post("http://127.0.0.1:3000/api/auth/login",json={"username":username,"password":password})
            if response.status_code!=200:
                raise RuntimeError(f"Zetaris login failed (HTTP {response.status_code})")
            login=response.json()
            org=str(login.get("orgId") or "1")
            headers={"Authorization":"Bearer "+login["idToken"],"X-Org-ID":org,"X-Request-ID":str(uuid.uuid4())}
            response=http.post("http://127.0.0.1:8888/api/v1.0/auth/api-key",headers=headers,json={"name":"sentry-ai-submission","expiryDate":"2026-11-07T23:59:59Z"})
            if response.status_code!=200 or not response.json().get("apiKey"):
                raise RuntimeError(f"Application key setup failed (HTTP {response.status_code}); no credentials logged")
            additions={"ZETARIS_BASE_URL":"http://127.0.0.1:8888/api/v1.0","ZETARIS_ORG_ID":org,"ZETARIS_API_TOKEN":response.json()["apiKey"]}
            with root_env.open("a",encoding="utf8") as f:
                f.write("\n"+"\n".join(f"{k}={v}" for k,v in additions.items())+"\n")
            current.update(additions)
    for key,value in current.items():
        if key.startswith("ZETARIS_"):
            os.environ[key]=value
    secret=ROOT/"local_data"/"pg_reader_password"
    if not secret.exists():
        secret.parent.mkdir(exist_ok=True,parents=True)
        secret.write_text(secrets.token_hex(20),encoding="utf8")
    reader=secret.read_text().strip()
    def psql(db,sql):
        result=subprocess.run(["docker","exec","-i","zetaris-postgres-1","psql","-v","ON_ERROR_STOP=1","-q","-U","zetaris","-d",db],input=sql,text=True,capture_output=True)
        if result.returncode:
            raise RuntimeError("Namespaced PostgreSQL setup failed; diagnostic withheld to protect credentials")
    psql("postgres",f"SELECT 'CREATE ROLE sentry_reader LOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sentry_reader')\\gexec\nALTER ROLE sentry_reader WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '{reader}';\nSELECT 'CREATE DATABASE sentry_hackathon_dev' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname='sentry_hackathon_dev')\\gexec\n")
    psql("sentry_hackathon_dev",(ROOT/"backend/zetaris_dataset/postgres_orders.sql").read_text())
    psql("sentry_hackathon_dev","REVOKE ALL ON DATABASE sentry_hackathon_dev FROM PUBLIC; GRANT CONNECT ON DATABASE sentry_hackathon_dev TO sentry_reader; GRANT USAGE ON SCHEMA public TO sentry_reader; GRANT SELECT ON ALL TABLES IN SCHEMA public TO sentry_reader;")
    for table in ("suppliers","inventory","status_updates"):
        directory=f"/home/zetaris/customer-data/shared/sentry_hackathon_dev/{table}"
        content=(ROOT/f"backend/zetaris_dataset/{table}.csv").read_bytes()
        subprocess.run(["docker","exec","-i","zetaris-driver-1","sh","-c",f"mkdir -p '{directory}' && cat > '{directory}/{table}.csv'"],input=content,check=True,capture_output=True)
    with ZetarisClient(ZetarisConfig.from_env()) as client:
        setup=statements(reader)+[("logistics database",'CREATE LIGHTNING DATABASE SENTRY_LOGISTICS_PORTAL DESCRIBE BY "Sentry AI synthetic carrier and supplier updates" OPTIONS ()'),("logistics table",'CREATE LIGHTNING FILESTORE TABLE status_updates FROM SENTRY_LOGISTICS_PORTAL FORMAT csv OPTIONS (path "file:///home/zetaris/customer-data/shared/sentry_hackathon_dev/status_updates", header "true")')]
        for label,sql in setup:
            try:
                client.execute_admin(sql)
            except ZetarisQueryError as exc:
                if "already exists" not in str(exc):
                    raise RuntimeError(f"Registration failed for {label}; diagnostic withheld") from None
            print(f"Registered/kept {label}")
    print("Namespaced data sources ready; credentials remain private")

if __name__=="__main__":
    main()
