"""Register the two Sentry AI development sources in Zetaris. Idempotent.

Run by seed_zetaris_dev.sh after the PostgreSQL database and CSV files exist. Needs the
ZETARIS_* settings (environment or repository-root .env) and SENTRY_PG_READER_PASSWORD.
These are the only write statements in the integration; the application path is read-only.
"""

import os
import sys

from app.data.zetaris_repository import ERP_SOURCE, PORTAL_SOURCE
from app.integrations.zetaris import ZetarisClient, ZetarisConfig, ZetarisQueryError
from scripts.zetaris_smoke import load_env

PG_JDBC_URL = os.environ.get("SENTRY_PG_JDBC_URL", "jdbc:postgresql://postgres:5432/sentry_hackathon_dev")
FILES_URL = os.environ.get("SENTRY_FILESTORE_URL", "file:///home/zetaris/customer-data/shared/sentry_hackathon_dev")


def statements(reader_password: str) -> list[tuple[str, str]]:
    quoted_password = reader_password.replace("\\", "\\\\").replace('"', '\\"')
    return [
        (f"datasource {ERP_SOURCE}",
         f'CREATE DATASOURCE {ERP_SOURCE} DESCRIBE BY "Sentry AI hackathon dev synthetic ERP orders, PostgreSQL" '
         f'OPTIONS (jdbcdriver "org.postgresql.Driver", jdbcurl "{PG_JDBC_URL}", '
         f'username "sentry_reader", password "{quoted_password}")'),
        (f"tables of {ERP_SOURCE}", f"REGISTER DATASOURCE TABLES FROM {ERP_SOURCE}"),
        (f"database {PORTAL_SOURCE}",
         f'CREATE LIGHTNING DATABASE {PORTAL_SOURCE} '
         f'DESCRIBE BY "Sentry AI hackathon dev synthetic supplier portal exports, CSV" OPTIONS ()'),
        *[(f"table {PORTAL_SOURCE}.{table}",
           f'CREATE LIGHTNING FILESTORE TABLE {table} FROM {PORTAL_SOURCE} FORMAT csv '
           f'OPTIONS (path "{FILES_URL}/{table}", header "true")')
          for table in ("suppliers", "inventory")],
    ]


def drop() -> int:
    """Unregister both sources (used by teardown_zetaris_dev.sh). Leaves the Zetaris sample data alone."""
    with ZetarisClient(ZetarisConfig.from_env()) as client:
        for sql in (f"DROP DATASOURCE {ERP_SOURCE}", f"DROP LIGHTNING DATABASE {PORTAL_SOURCE}"):
            try:
                client.execute_admin(sql)
                print(f"      {sql}")
            except ZetarisQueryError as exc:
                print(f"      skipped {sql}: {exc}")
    return 0


def main() -> int:
    load_env()
    if "--drop" in sys.argv[1:]:
        return drop()
    password = os.environ.get("SENTRY_PG_READER_PASSWORD", "")
    if not password:
        print("SENTRY_PG_READER_PASSWORD is required (seed_zetaris_dev.sh supplies it)")
        return 2
    with ZetarisClient(ZetarisConfig.from_env()) as client:
        for label, sql in statements(password):
            try:
                client.execute_admin(sql)
                print(f"      registered {label}")
            except ZetarisQueryError as exc:
                if "already exists" not in str(exc):
                    raise
                print(f"      kept existing {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
