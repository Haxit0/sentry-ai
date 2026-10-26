#!/usr/bin/env bash
# Load the Sentry AI synthetic dataset into two independent sources that the local
# Zetaris platform federates, then register them in Zetaris.
#
#   PostgreSQL  database sentry_hackathon_dev, table public.customer_orders
#               (on the Zetaris compose Postgres server; separate from its metastore/audit
#               databases; Zetaris reads it as the read-only role sentry_reader)
#   Filestore   CSV files under customer-data/shared/sentry_hackathon_dev/ in the driver
#
# Idempotent. Touches only the namespaced objects above; never Zetaris's own databases,
# volumes, compose files or credentials. Undo with teardown_zetaris_dev.sh.
#
# Usage, from backend/:  bash scripts/seed_zetaris_dev.sh
# Needs: docker, the running zetaris-platform stack, ../.env with ZETARIS_* settings.

set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$(dirname "$HERE")"
DATASET="$BACKEND/zetaris_dataset"
PG_CONTAINER="${ZETARIS_PG_CONTAINER:-zetaris-postgres-1}"
DRIVER_CONTAINER="${ZETARIS_DRIVER_CONTAINER:-zetaris-driver-1}"
PG_SUPERUSER="${ZETARIS_PG_SUPERUSER:-zetaris}"
DB=sentry_hackathon_dev
READER=sentry_reader
FILES_DIR=/home/zetaris/customer-data/shared/sentry_hackathon_dev
SECRET_FILE="${SENTRY_PG_READER_PASSWORD_FILE:-$HOME/.config/sentry-ai/pg_reader_password}"

python_bin="${PYTHON:-$BACKEND/../.venv/bin/python}"
"$python_bin" -m scripts.zetaris_dataset --check >/dev/null || {
    echo "zetaris_dataset/ is stale: run python -m scripts.zetaris_dataset first" >&2; exit 1; }

# The reader password is generated once and kept outside the repository (mode 600).
if [ ! -s "$SECRET_FILE" ]; then
    mkdir -p "$(dirname "$SECRET_FILE")"
    (umask 077; head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$SECRET_FILE")
fi
READER_PASSWORD="$(cat "$SECRET_FILE")"

psql_su() { docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -q -U "$PG_SUPERUSER" "$@"; }

echo "[1/3] PostgreSQL: database $DB, read-only role $READER, table public.customer_orders"
# Password goes over stdin as a psql variable, never on a command line.
psql_su -d postgres -v reader_pw="$READER_PASSWORD" <<SQL
SELECT 'CREATE ROLE $READER LOGIN' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$READER')\gexec
ALTER ROLE $READER WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'reader_pw';
SELECT 'CREATE DATABASE $DB' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '$DB')\gexec
SQL
psql_su -d "$DB" < "$DATASET/postgres_orders.sql"
psql_su -d "$DB" <<SQL
REVOKE ALL ON DATABASE $DB FROM PUBLIC;
GRANT CONNECT ON DATABASE $DB TO $READER;
GRANT USAGE ON SCHEMA public TO $READER;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO $READER;
SQL
echo "      rows: $(psql_su -d "$DB" -Atc 'select count(*) from public.customer_orders' </dev/null)"

echo "[2/3] Filestore: CSV files in $FILES_DIR"
for table in suppliers inventory; do
    # Written as the driver's own user so Zetaris can read it; one directory per table.
    docker exec -i "$DRIVER_CONTAINER" sh -c "mkdir -p '$FILES_DIR/$table' && cat > '$FILES_DIR/$table/$table.csv'" \
        < "$DATASET/$table.csv"
done
docker exec "$DRIVER_CONTAINER" sh -c "wc -l '$FILES_DIR'/*/*.csv"

echo "[3/3] Zetaris: register both sources"
SENTRY_PG_READER_PASSWORD="$READER_PASSWORD" "$python_bin" -m scripts.register_zetaris_sources
