import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.pool import NullPool


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def env_path() -> Path:
    return project_root() / ".env"


def load_tracker_env() -> None:
    load_dotenv(env_path(), override=False)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def normalize_database_url(value: str | None) -> str | None:
    if value and value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql://", 1)
    return value


def get_database_url() -> str | None:
    return normalize_database_url(os.environ.get("DATABASE_URL"))


def get_central_db_url() -> str | None:
    return normalize_database_url(os.environ.get("CENTRAL_DB_URL") or os.environ.get("DATABASE_URL"))


def is_pooled_postgres_url(url: str | None) -> bool:
    normalized = normalize_database_url(url) or ""
    if not normalized.startswith("postgresql://"):
        return False
    return "pooler" in normalized.lower()


def get_sqlalchemy_engine_options(url: str | None, *, serverless_default: bool = True) -> dict:
    if not url:
        return {}

    normalized = normalize_database_url(url) or ""
    if not normalized.startswith("postgresql://"):
        return {}

    use_null_pool = env_bool("DB_USE_NULL_POOL", serverless_default and env_bool("VERCEL", False))
    if use_null_pool:
        return {
            "poolclass": NullPool,
            "pool_pre_ping": True,
        }

    pool_size = max(1, env_int("DB_POOL_SIZE", 5))
    max_overflow = max(0, env_int("DB_MAX_OVERFLOW", 5))
    pool_timeout = max(5, env_int("DB_POOL_TIMEOUT", 30))
    pool_recycle = max(60, env_int("DB_POOL_RECYCLE", 300))

    return {
        "pool_pre_ping": True,
        "pool_recycle": pool_recycle,
        "pool_timeout": pool_timeout,
        "pool_use_lifo": True,
        "pool_size": pool_size,
        "max_overflow": max_overflow,
    }


def get_sync_settings() -> dict:
    return {
        "database_url": get_database_url(),
        "interval_seconds": max(3, env_int("SYNC_INTERVAL_SECONDS", 5)),
        "change_monitoring": env_bool("SYNC_CHANGE_MONITORING", True),
        "worker_name": os.environ.get("SYNC_WORKER_NAME", "erp-sync"),
        "worker_mode": os.environ.get("SYNC_WORKER_MODE", "pi"),
    }


def get_mirror_sync_settings() -> dict:
    return {
        "heartbeat_interval_seconds": max(3, env_int("SYNC_HEARTBEAT_INTERVAL_SECONDS", 5)),
        "master_cadence_seconds": max(30, env_int("SYNC_MASTER_CADENCE_SECONDS", 300)),
        "operational_cadence_seconds": max(3, env_int("SYNC_OPERATIONAL_CADENCE_SECONDS", 5)),
        "ar_cadence_seconds": max(30, env_int("SYNC_AR_CADENCE_SECONDS", 300)),
        "document_cadence_seconds": max(30, env_int("SYNC_DOCUMENT_CADENCE_SECONDS", 300)),
        "batch_size": max(100, env_int("SYNC_BATCH_SIZE", 1000)),
        "staging_schema": os.environ.get("MIRROR_STAGING_SCHEMA", "public"),
        "worker_name": os.environ.get("SYNC_WORKER_NAME", "erp-sync"),
        "worker_mode": os.environ.get("SYNC_WORKER_MODE", "pi"),
    }


def get_sql_server_settings() -> dict:
    dsn = (os.environ.get("SQLSERVER_DSN") or "").strip()
    if dsn:
        return {"mode": "dsn", "dsn": dsn}

    server = (os.environ.get("SQLSERVER_SERVER") or "").strip()
    database = (os.environ.get("SQLSERVER_DB") or "").strip()
    user = (os.environ.get("SQLSERVER_USER") or "").strip()
    password = (os.environ.get("SQLSERVER_PASSWORD") or "").strip()
    driver = (os.environ.get("SQLSERVER_DRIVER") or "").strip()

    legacy_host = (os.environ.get("SQL_HOST") or "").strip()
    legacy_db = (os.environ.get("SQL_DB") or "").strip()
    legacy_user = (os.environ.get("SQL_USER") or "").strip()
    legacy_password = (os.environ.get("SQL_PASSWORD") or "").strip()
    legacy_port = (os.environ.get("SQL_PORT") or "").strip()
    legacy_driver = (os.environ.get("ODBC_DRIVER") or "").strip()

    if legacy_host:
        server = legacy_host
        if legacy_port and "," not in server:
            server = f"{server},{legacy_port}"
    if legacy_db:
        database = legacy_db
    if legacy_user:
        user = legacy_user
    if legacy_password:
        password = legacy_password
    if legacy_driver:
        driver = legacy_driver

    if not driver:
        driver = "ODBC Driver 17 for SQL Server"
    if not driver.startswith("{"):
        driver = f"{{{driver}}}"

    trusted = not (user and password)
    return {
        "mode": "connection_string",
        "server": server,
        "database": database,
        "user": user,
        "password": password,
        "driver": driver,
        "trusted": trusted,
    }


def sql_connection_configured() -> bool:
    settings = get_sql_server_settings()
    if settings["mode"] == "dsn":
        return bool(settings.get("dsn"))
    return bool(settings.get("server") and settings.get("database"))


def build_sql_connection_strings() -> list[str]:
    settings = get_sql_server_settings()
    if settings["mode"] == "dsn":
        return [f"DSN={settings['dsn']};"]

    if not sql_connection_configured():
        return []

    base = (
        f"DRIVER={settings['driver']};"
        f"SERVER={settings['server']};"
        f"DATABASE={settings['database']};"
    )

    auth = "Trusted_Connection=yes;" if settings["trusted"] else f"UID={settings['user']};PWD={settings['password']};"
    return [
        f"{base}{auth}Encrypt=no;TrustServerCertificate=yes;",
        f"{base}{auth}Encrypt=yes;TrustServerCertificate=yes;",
        f"{base}{auth}",
    ]


load_tracker_env()
