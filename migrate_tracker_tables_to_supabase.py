import os
from collections import OrderedDict

from dotenv import dotenv_values
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text

from app.Models import models  # noqa: F401
from app.extensions import db


CORE_TABLES = [
    "PickTypes",
    "pickster",
    "pick",
    "pick_assignments",
    "work_orders",
    "customer_notes",
    "audit_events",
    "credit_images",
]

# Legacy cache tables (erp_mirror_picks, erp_mirror_work_orders, erp_delivery_kpis)
# have been retired and dropped. See docs/FINAL_RETIREMENT_OF_LEGACY_MIRROR.md.

TABLES_IN_INSERT_ORDER = CORE_TABLES

TABLES_IN_TRUNCATE_ORDER = list(reversed(TABLES_IN_INSERT_ORDER))
INSERT_BATCH_SIZE = 1000


def _load_urls() -> tuple[str, str]:
    tracker_env = dotenv_values(r"C:\Users\amcgrean\python\tracker\.env")
    api_env = dotenv_values(r"C:\Users\amcgrean\python\api\.env")

    source_url = (
        os.environ.get("SOURCE_DATABASE_URL")
        or os.environ.get("TRACKER_LEGACY_DB_URL")
        or tracker_env.get("DATABASE_URL")
    )
    target_url = (
        os.environ.get("TARGET_DATABASE_URL")
        or os.environ.get("SUPABASE_DATABASE_URL")
        or api_env.get("DATABASE_URL")
    )

    if not source_url:
        raise RuntimeError("Missing source database URL.")
    if not target_url:
        raise RuntimeError("Missing target database URL.")
    return source_url, target_url


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _ensure_tables_exist(target_engine) -> None:
    existing = set(inspect(target_engine).get_table_names())
    missing = [name for name in TABLES_IN_INSERT_ORDER if name not in existing and name in db.metadata.tables]
    if not missing:
        return
    db.metadata.create_all(bind=target_engine, tables=[db.metadata.tables[name] for name in missing])


def _target_columns(engine, table_name: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :table_name
                """
            ),
            {"table_name": table_name},
        ).fetchall()
    return {row[0] for row in rows}


def _fetch_rows(engine, table_name: str) -> list[dict]:
    table = Table(table_name, MetaData(), autoload_with=engine)
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(select(table)).mappings()]


def _reset_sequence(conn, table_name: str) -> None:
    table = db.metadata.tables.get(table_name)
    if table is None or "id" not in table.columns:
        return
    seq_sql = text(
        """
        SELECT setval(
            pg_get_serial_sequence(:table_name, 'id'),
            COALESCE((SELECT MAX(id) FROM %s), 1),
            COALESCE((SELECT MAX(id) FROM %s), 0) > 0
        )
        """
        % (_quoted(table_name), _quoted(table_name))
    )
    conn.execute(seq_sql, {"table_name": table_name})


def _insert_rows(conn, table_name: str, rows: list[dict]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    column_sql = ", ".join(_quoted(column) for column in columns)
    value_sql = ", ".join(f":{column}" for column in columns)
    statement = text(f"INSERT INTO {_quoted(table_name)} ({column_sql}) VALUES ({value_sql})")
    for start in range(0, len(rows), INSERT_BATCH_SIZE):
        conn.execute(statement, rows[start:start + INSERT_BATCH_SIZE])


def main() -> None:
    source_url, target_url = _load_urls()
    source_engine = create_engine(source_url, connect_args={"options": "-c statement_timeout=0"})
    target_engine = create_engine(target_url, connect_args={"options": "-c statement_timeout=0"})

    print("Source:", source_url)
    print("Target:", target_url)

    _ensure_tables_exist(target_engine)

    source_tables = set(inspect(source_engine).get_table_names())
    target_tables = set(inspect(target_engine).get_table_names())

    rows_by_table: OrderedDict[str, list[dict]] = OrderedDict()
    for table_name in TABLES_IN_INSERT_ORDER:
        if table_name not in source_tables:
            print(f"Skipping missing source table: {table_name}")
            continue
        if table_name not in target_tables:
            raise RuntimeError(f"Target table missing after create_all: {table_name}")
        rows = _fetch_rows(source_engine, table_name)
        rows_by_table[table_name] = rows
        print(f"Loaded {len(rows)} rows from {table_name}")

    with target_engine.begin() as conn:
        for table_name in TABLES_IN_TRUNCATE_ORDER:
            if table_name in rows_by_table:
                conn.execute(text(f"TRUNCATE TABLE {_quoted(table_name)} RESTART IDENTITY CASCADE"))

        for table_name, rows in rows_by_table.items():
            target_columns = _target_columns(target_engine, table_name)
            filtered_rows = [{key: value for key, value in row.items() if key in target_columns} for row in rows]
            _insert_rows(conn, table_name, filtered_rows)
            _reset_sequence(conn, table_name)
            count = conn.execute(text(f"SELECT COUNT(*) FROM {_quoted(table_name)}")).scalar()
            print(f"Target {table_name}: {count} rows")

    print("Tracker table migration complete.")


if __name__ == "__main__":
    main()
