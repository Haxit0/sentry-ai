# Zetaris integration

Status (2026-10-26): **the live data layer works against a real local Zetaris platform; the HTTP API is still fixture-only.** `ZetarisRepository.snapshot()` returns validated `DemoData` from real Zetaris queries over two independent sources, and the unchanged deterministic simulator reproduces the golden answer from it. Serving that through `/api` requires the contract change proposed [below](#proposed-contract-change-not-implemented), so `/api/health` still reports `zetaris: not_configured` and every API response is fixture data.

## Why Zetaris matters to Sentry AI

A supply-chain disruption investigation needs facts that live in different systems: customer orders and penalties in an ERP database, supplier schedules, expedite offers and alternative-supplier quotes in supplier-portal exports, stock in a warehouse system. Sentry AI uses Zetaris as the single SQL layer over those sources, without copying them into a new store first.

The application reads customer orders from **PostgreSQL** (registered in Zetaris as a JDBC datasource) and supplier offers plus on-hand inventory from **CSV files** (a Zetaris Lightning filestore database). It fetches orders with **one cross-source SQL join** executed by Zetaris:

```sql
SELECT o.order_id, o.customer_name, o.supplier_id, o.sku, o.quantity, o.promised_date,
       o.penalty_per_day_gbp, s.sku AS supplier_sku
FROM SENTRY_ERP_PG.customer_orders o
LEFT JOIN SENTRY_SUPPLIER_PORTAL.suppliers s ON o.supplier_id = s.supplier_id
ORDER BY o.order_id
```

So an order whose supplier is missing from the supplier portal, or whose SKU disagrees with it, is detected across the two systems and rejected, not silently dropped. Every figure the simulator computes from that data carries a provenance label naming the Zetaris source and record (for example `zetaris://SENTRY_ERP_PG.customer_orders/ORD-1002`) instead of the local fixture file. The records are synthetic; the sources, the federation and the queries are real.

## Architecture

```text
scripts/zetaris_smoke.py, tests/test_zetaris_live.py      (opt-in live entry points)
        │
app/services/simulation.py   simulate(request, repository)   unchanged maths; evidence labels come from the repository
        │ DataRepository.snapshot() -> DemoData
app/data/zetaris_repository.py   ZetarisRepository   3 bounded SELECTs, exact parsing, shared validation, provenance
app/data/validation.py           validate_snapshot   identical rules for fixture and Zetaris data
        │ SQL text → string cells
app/integrations/zetaris.py      ZetarisClient       auth headers, timeouts, read-only guard, error mapping
        │ POST /api/v1.0/sql-editor/sqls/run
Zetaris platform (local Docker)  ── JDBC ──▶ PostgreSQL: sentry_hackathon_dev.public.customer_orders
                                 ── file ──▶ CSV: customer-data/shared/sentry_hackathon_dev/{suppliers,inventory}/
```

The simulator never sees the REST protocol. `ZetarisRepository` never falls back to fixture data: a failed or inconsistent live query raises a `ZetarisError` subclass and returns nothing.

## Data sources

| Zetaris name | Kind | Physical location | Tables | Holds |
| --- | --- | --- | --- | --- |
| `SENTRY_ERP_PG` | JDBC datasource (PostgreSQL 16, `org.postgresql.Driver`) | database `sentry_hackathon_dev` on the Zetaris compose Postgres server, read as role `sentry_reader` (SELECT only) | `customer_orders` | 6 orders |
| `SENTRY_SUPPLIER_PORTAL` | Lightning database, filestore tables, CSV with header | `/home/zetaris/customer-data/shared/sentry_hackathon_dev/` in the driver's `customer-data` volume | `suppliers`, `inventory` | 3 suppliers with expedite and alternative offers; 3 SKUs of stock |

The development database lives on the same Postgres **server** that Zetaris uses for its own metastore, but it is a separate database with its own read-only role; Zetaris reaches it over JDBC exactly as it would an external ERP. The two sources use different Zetaris connectors (JDBC versus filestore) and different storage, so the join above is genuine federation, not two tables in one database.

All records are generated from `backend/app/data/demo_data.json` by `backend/scripts/zetaris_dataset.py` into `backend/zetaris_dataset/` (`postgres_orders.sql`, `suppliers.csv`, `inventory.csv`). A test fails if those files drift from the fixture.

## Loading and removing the dataset

Prerequisites: the `zetaris-platform` stack running (`./verify.sh` passes), Docker access from WSL, the repository virtual environment, and the settings below in the repository-root `.env`.

```bash
cd backend
python -m scripts.zetaris_dataset        # only if demo_data.json changed
bash scripts/seed_zetaris_dev.sh         # idempotent
bash scripts/teardown_zetaris_dev.sh     # removes everything the seed created
```

`seed_zetaris_dev.sh` creates only these namespaced objects:

1. PostgreSQL: role `sentry_reader` (LOGIN, no other privileges), database `sentry_hackathon_dev`, table `public.customer_orders`; `CONNECT` plus `SELECT` for the role. The role password is generated once into `~/.config/sentry-ai/pg_reader_password` (mode 600, outside the repository) and passed to psql and Zetaris over stdin or HTTPS bodies, never on a command line.
2. Files: `suppliers/suppliers.csv` and `inventory/inventory.csv` under `customer-data/shared/sentry_hackathon_dev/`, written as the driver's own user.
3. Zetaris, via `scripts/register_zetaris_sources.py`: `CREATE DATASOURCE SENTRY_ERP_PG … OPTIONS (jdbcdriver, jdbcurl, username, password)`, `REGISTER DATASOURCE TABLES FROM SENTRY_ERP_PG`, `CREATE LIGHTNING DATABASE SENTRY_SUPPLIER_PORTAL`, and `CREATE LIGHTNING FILESTORE TABLE suppliers|inventory … FORMAT csv OPTIONS (path, header "true")`. Objects that already exist are kept.

The teardown runs `DROP DATASOURCE SENTRY_ERP_PG`, `DROP LIGHTNING DATABASE SENTRY_SUPPLIER_PORTAL`, `DROP DATABASE sentry_hackathon_dev`, `DROP ROLE sentry_reader` and removes the CSV directory. It never touches the Zetaris `metastore`/`audit` databases, the `NY_TAXI`/`TPCDS_DB` sample data, volumes, compose files or the admin account. Both scripts were run end to end: teardown, seed from scratch, then the smoke test passed.

Two platform behaviours shaped this: `REGISTER DATASOURCE TABLES` only discovers tables in the JDBC default schema (a table in another schema registered "0 injected"), so the table is in `public`; and datasource descriptions accept only letters, digits, spaces and `_ . - ,`.

## Configuration

Repository-root `.env` (git-ignored; never commit it):

| Variable | Required | Meaning |
| --- | --- | --- |
| `ZETARIS_BASE_URL` | yes | REST base including version, e.g. `http://127.0.0.1:8888/api/v1.0` |
| `ZETARIS_API_TOKEN` | yes | Zetaris API key, sent as `Authorization: Bearer …` |
| `ZETARIS_ORG_ID` | yes | Numeric organisation id, sent as `X-Org-ID` (the local install uses `1`; it is not always 1) |
| `ZETARIS_CONNECT_TIMEOUT_SECONDS` | no | Default 5 |
| `ZETARIS_READ_TIMEOUT_SECONDS` | no | Default 60 (Spark's first query after a restart can take ~10 s) |

Create an API key in the Zetaris UI, or with the REST API while signed in: `POST /api/v1.0/auth/api-key` with `{"name": "...", "expiryDate": "2026-12-31T23:59:59Z"}`; the response's `apiKey` is shown once. Keys are listed and revoked at `GET`/`DELETE /api/v1.0/auth/api-key[/{id}]`. The key used in development is named `sentry-ai-dev-hackathon` and expires 2026-12-31.

`ZetarisRepository()` never reads the environment by itself; live mode is the explicit `ZetarisRepository.from_env()`.

## The verified REST call

Confirmed against the running platform (Zetaris API 2.4.3.1) and its endpoint definitions:

```http
POST /api/v1.0/sql-editor/sqls/run
Authorization: Bearer <API key>
X-Org-ID: 1
X-Request-ID: <fresh UUID per request>
Content-Type: application/json

{"queryId": "<fresh UUID>", "sql": "SELECT …", "source": "Generic", "limit": 1001}
```

```json
{"headers": ["sku", "on_hand_units"], "data": [["SKU-CASING", "5"], ["SKU-CONTROL", "6"], ["SKU-SENSOR", "10"]], "total": 3, "timeUsed": 252}
```

`queryId` must be a UUID string and `source` one of `SqlEditor`, `TablePreview`, `PipelineNodePreview`, `QueryBuilder`, `Generic`. Every cell is a string or null. PostgreSQL `numeric(14,2)` arrives as `decimal(38,18)` text such as `"100.000000000000000000"`; the repository converts it with `Decimal` and rejects anything that is not a whole number of pennies rather than rounding. Dates must be `YYYY-MM-DD`.

The client's read-only path accepts exactly one `SELECT` with no `;` and none of the DDL/DML keywords; identifiers are checked against `[A-Za-z_][A-Za-z0-9_]{0,63}` and come from constants (no request value is ever placed in SQL; supplier selection happens in Python). It asks for `max_rows + 1` rows and refuses the result if more come back, instead of working on a truncated set. Only the registration script uses the separate `execute_admin` path.

## Read-only queries to try in the Zetaris SQL Editor

Open <http://localhost:3000>, sign in, open the SQL Editor and run:

```sql
SHOW DATASOURCES;                                   -- SENTRY_ERP_PG
SHOW DATASOURCE TABLES SENTRY_ERP_PG;               -- customer_orders
SHOW LIGHTNING DATABASES;                           -- SENTRY_SUPPLIER_PORTAL, NY_TAXI, TPCDS_DB
SELECT * FROM SENTRY_ERP_PG.customer_orders ORDER BY order_id;
SELECT * FROM SENTRY_SUPPLIER_PORTAL.suppliers ORDER BY supplier_id;
SELECT * FROM SENTRY_SUPPLIER_PORTAL.inventory ORDER BY sku;
SELECT o.order_id, o.supplier_id, s.restock_date, i.on_hand_units
FROM SENTRY_ERP_PG.customer_orders o
JOIN SENTRY_SUPPLIER_PORTAL.suppliers s ON o.supplier_id = s.supplier_id
JOIN SENTRY_SUPPLIER_PORTAL.inventory i ON o.sku = i.sku
ORDER BY o.order_id;
```

## Running the tests

From `backend` with the repository virtual environment:

```bash
python -m pytest -q                                          # offline: fixture + mocked Zetaris tests; live test skipped
ZETARIS_LIVE_TESTS=1 python -m pytest tests/test_zetaris_live.py -v -s   # real platform
python -m scripts.zetaris_smoke                              # real platform, human-readable report
```

`tests/test_zetaris.py` uses `httpx.MockTransport` responses shaped like the real platform's. It covers authenticated request headers and bodies, mapping to the shared types, missing or cross-source-orphaned records, malformed dates, amounts, integers and nulls, duplicates, unexpected columns and shapes, bad credentials (including Zetaris's `400 Not Allowed`), unavailable and 5xx platforms, connect and read timeouts, unsafe identifiers and non-SELECT SQL, oversized results, provenance, simulator equality with the fixture across 12 scenarios, and dataset drift.

The smoke script prints the sources queried, row counts, query ids and timings, the validation result and the Alpha +5 simulation; it never prints tokens or headers.

## Errors and troubleshooting

| Exception | Cause | What to check |
| --- | --- | --- |
| `IntegrationNotConfigured` | A `ZETARIS_*` setting is missing or the org id is not numeric | `.env` |
| `ZetarisAuthError` | 401/403, or Zetaris's `400 Not Allowed` for a wrong or expired API key or org id | Key expiry and org id; create a new key |
| `ZetarisUnavailable` | Connection refused, connect or read timeout, HTTP 5xx | `docker compose ps` in `~/zetaris-platform`, then `./verify.sh`; the driver takes minutes after a restart |
| `ZetarisQueryError` | Zetaris rejected the SQL (message included, stack trace stripped) or returned an unexpected response shape | `TABLE_OR_VIEW_NOT_FOUND` means the dataset is not registered: run `seed_zetaris_dev.sh` |
| `ZetarisDataError` | The query worked but records are missing, duplicated, malformed, cross-source inconsistent or over the row cap | The message names the source table and record |

If the platform was reset (for example `docker compose down -v`), re-run the seed: registrations live in the Zetaris metastore and the CSVs in its volume.

## What was actually tested (2026-10-26, local Windows 11 + WSL2 + Docker Desktop)

| Check | Result |
| --- | --- |
| Authenticated `sqls/run` with an API key | Real: 200, `select 7` returned `[["7"]]` |
| Orders from PostgreSQL through Zetaris | Real: 6 rows from `SENTRY_ERP_PG.customer_orders` |
| Suppliers and inventory from CSV through Zetaris | Real: 3 + 3 rows from `SENTRY_SUPPLIER_PORTAL` |
| Cross-source join | Real: 6 rows joining PostgreSQL orders to CSV suppliers (and inventory in the SQL Editor query) |
| `ZetarisRepository.snapshot()` validation | Real: passed (3 suppliers, 6 orders, 3 SKUs) |
| Simulator on Zetaris data | Real: Alpha +5 → exposure £500.00, `expedite_shipping` £160.00; evidence cites only `zetaris://` sources |
| Wrong API key / wrong org id | Real: `ZetarisAuthError` |
| Nothing listening | Real: `ZetarisUnavailable` |
| Teardown, re-seed from scratch, smoke test | Real: passed |
| Unit suite on Python 3.12 and 3.11 | 105 passed, 1 skipped (the live test) |
| Fixture API on port 8000 | Real: health unchanged, Alpha +5 £500/£160 with `demo_data.json` evidence, zero delay £0.00, unknown supplier 404 |

Read timeouts and 5xx responses were exercised with mocks only.

## Proposed contract change (not implemented)

Serving live data through `/api` needs team agreement because v1 freezes these literals:

1. `SimulationResponse.execution_mode` and `HealthResponse.execution_mode`: allow `"zetaris"` alongside `"fixture"`.
2. `IntegrationStatuses.zetaris`: allow `"connected"` (last snapshot succeeded) and `"unavailable"` (configured but failing) besides `"not_configured"`.
3. The disclaimer: a Zetaris-mode variant saying the records come from Zetaris (still synthetic, costs still hypothetical). Today `simulate()` over Zetaris data still says `execution_mode: "fixture"` and "no Zetaris … connected", which is why live mode is not exposed.
4. Mode selection: a server-side setting `SENTRY_DATA_MODE=fixture|zetaris` (default `fixture`) read once in `main.get_repository`, with no request-level switch. In `zetaris` mode a `ZetarisError` maps to HTTP 503 `{"detail": "Zetaris unavailable: …"}` and never to fixture results.

Fixture-mode responses stay byte-identical; the frontend needs only widened union types. The one change already made outside Developer 1's files is in `app/services/simulation.py` (Developer 2): evidence `source` labels come from the repository (`evidence_source()`), so fixture labels are unchanged and live labels name Zetaris.

## Limitations

- The API remains fixture-only until the change above is agreed.
- The datasets are synthetic and tiny (3/6/3 records). The 1,000-row cap and three full-table reads suit this dataset, not production volumes; a larger dataset would push the supplier filter into the SQL with an allowlisted literal or a view.
- The PostgreSQL source shares a server with the Zetaris metastore (separate database and role). A fully separate ERP host would only change `SENTRY_PG_JDBC_URL`.
- CSV cells are untyped; all typing and validation happen in the repository.
- The evaluation date stays fixed at 2026-10-25 as the contract requires.
- The API key expires 2026-12-31 and the reader password lives only on this machine; teammates need their own key and a seed run against their own Zetaris.
