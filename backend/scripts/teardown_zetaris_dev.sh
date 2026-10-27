#!/usr/bin/env bash
# Remove everything seed_zetaris_dev.sh created, and nothing else:
#   Zetaris datasource SENTRY_ERP_PG and Lightning database SENTRY_SUPPLIER_PORTAL
#   PostgreSQL database sentry_hackathon_dev and role sentry_reader
#   CSV files under customer-data/shared/sentry_hackathon_dev in the driver
# The Zetaris metastore/audit databases, sample data, volumes and compose files are untouched.
#
# Usage, from backend/:  bash scripts/teardown_zetaris_dev.sh

set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(dirname "$HERE")"
PG_CONTAINER="${ZETARIS_PG_CONTAINER:-zetaris-postgres-1}"
DRIVER_CONTAINER="${ZETARIS_DRIVER_CONTAINER:-zetaris-driver-1}"
PG_SUPERUSER="${ZETARIS_PG_SUPERUSER:-zetaris}"
python_bin="${PYTHON:-$BACKEND/../.venv/bin/python}"

echo "[1/3] Zetaris: unregister sources"
(cd "$BACKEND" && "$python_bin" -m scripts.register_zetaris_sources --drop)

echo "[2/3] PostgreSQL: drop database sentry_hackathon_dev and role sentry_reader"
docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -q -U "$PG_SUPERUSER" -d postgres <<'SQL'
DROP DATABASE IF EXISTS sentry_hackathon_dev WITH (FORCE);
DROP ROLE IF EXISTS sentry_reader;
SQL

echo "[3/3] Filestore: remove CSV files"
docker exec "$DRIVER_CONTAINER" rm -rf /home/zetaris/customer-data/shared/sentry_hackathon_dev </dev/null
echo "done (the local reader password file, if any, is left at ~/.config/sentry-ai/)"
