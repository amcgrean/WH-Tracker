from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Protocol, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .config import TableSyncConfig


class SqlServerExtractor(Protocol):
    def fetch_rows(self, config: TableSyncConfig, *, watermark: datetime | None) -> Sequence[dict[str, Any]]:
        ...


@dataclass(slots=True)
class SyncTableResult:
    table_name: str
    extracted_rows: int = 0
    staged_rows: int = 0
    merged_rows: int = 0
    deleted_rows: int = 0
    duration_ms: int = 0
    status: str = "pending"
    error: str | None = None


@dataclass(slots=True)
class SyncBatchResult:
    batch_id: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str = "running"
    table_results: list[SyncTableResult] = field(default_factory=list)


class MirrorSyncFramework:
    def __init__(self, engine: Engine):
        self.engine = engine

    def run_table(
        self,
        config: TableSyncConfig,
        extractor: SqlServerExtractor,
        *,
        watermark: datetime | None = None,
    ) -> SyncTableResult:
        started = datetime.utcnow()
        result = SyncTableResult(table_name=config.table_name, status="running")

        try:
            rows = list(extractor.fetch_rows(config, watermark=watermark))
            result.extracted_rows = len(rows)
            if rows:
                self.stage_rows(config, rows)
                result.staged_rows = len(rows)
                result.merged_rows = self.merge_rows(config)
            result.status = "success"
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
            raise
        finally:
            result.duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)

        return result

    def stage_rows(self, config: TableSyncConfig, rows: Iterable[dict[str, Any]]) -> None:
        rows = list(rows)
        if not rows:
            return

        columns = list(rows[0].keys())
        insert_sql = text(
            f"""
            INSERT INTO {config.staging_table_name} ({", ".join(columns)})
            VALUES ({", ".join(f":{column}" for column in columns)})
            """
        )
        with self.engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {config.staging_table_name}"))
            conn.execute(insert_sql, rows)

    def merge_rows(self, config: TableSyncConfig) -> int:
        assignments = ", ".join(
            f"{column} = source.{column}"
            for column in self._merge_columns(config)
            if column not in config.natural_key_columns
        )
        key_predicate = " AND ".join(
            f"target.{column} = source.{column}" for column in config.natural_key_columns
        )
        insert_columns = self._merge_columns(config)
        insert_list = ", ".join(insert_columns)
        insert_values = ", ".join(f"source.{column}" for column in insert_columns)

        merge_sql = text(
            f"""
            MERGE INTO {config.table_name} AS target
            USING {config.staging_table_name} AS source
            ON {key_predicate}
            WHEN MATCHED THEN
                UPDATE SET {assignments}
            WHEN NOT MATCHED THEN
                INSERT ({insert_list})
                VALUES ({insert_values});
            """
        )
        with self.engine.begin() as conn:
            conn.execute(merge_sql)
        return 0

    def _merge_columns(self, config: TableSyncConfig) -> list[str]:
        inspector_sql = text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table_name
            ORDER BY ordinal_position
            """
        )
        with self.engine.begin() as conn:
            rows = conn.execute(inspector_sql, {"table_name": config.staging_table_name}).fetchall()
        return [row[0] for row in rows]
