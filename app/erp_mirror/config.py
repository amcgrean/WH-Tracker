from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SyncFamily(str, Enum):
    MASTER = "master"
    OPERATIONAL = "operational"
    AR = "ar"
    DOCUMENT = "document"


class SyncStrategy(str, Enum):
    INCREMENTAL = "incremental"
    REPLACE = "replace"
    WINDOWED = "windowed"
    FULL_REFRESH = "full_refresh"


@dataclass(slots=True)
class TableSyncConfig:
    table_name: str
    staging_table_name: str
    family: SyncFamily
    strategy: SyncStrategy
    natural_key_columns: tuple[str, ...]
    source_query: str
    source_updated_column: str | None = None
    delete_detection_enabled: bool = False
    cadence_seconds: int = 60
    batch_size: int = 1000
    indexed_columns: tuple[str, ...] = field(default_factory=tuple)
