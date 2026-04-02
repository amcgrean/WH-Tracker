import csv
import os
from datetime import date, datetime, timedelta
from functools import lru_cache

from sqlalchemy import bindparam, create_engine, func, inspect, text
from app.branch_utils import normalize_branch, expand_branch, expand_branch_filter
from app.extensions import db
from app.runtime_settings import (
    build_sql_connection_strings,
    env_bool,
    get_central_db_url,
    get_sql_server_settings,
    get_sqlalchemy_engine_options,
)

try:
    import pyodbc
except (ImportError, OSError):
    pyodbc = None

class ERPServiceBase:
    def __init__(self):
        self.sql_settings = get_sql_server_settings()
        self.cloud_mode = env_bool('CLOUD_MODE', True)
        self.allow_legacy_erp_fallback = env_bool('ENABLE_LEGACY_ERP_FALLBACK', False)

        # Central DB Mode: Active if CENTRAL_DB_URL (or DATABASE_URL fallback) is set.
        central_url = get_central_db_url() or ''
        self.central_db_mode = bool(central_url)

        print(
            "ERPService Init: "
            f"CLOUD_MODE={self.cloud_mode}, "
            f"CENTRAL_DB_MODE={self.central_db_mode}, "
            f"LEGACY_ERP_FALLBACK={self.allow_legacy_erp_fallback}"
        )
        self._gps_cache = None
        # Simple TTL cache for expensive sales queries: {key: (ts, data)}
        self._sales_cache: dict = {}

    # ------------------------------------------------------------------
    # Sales query cache helpers (per-instance, TTL in seconds)
    # ------------------------------------------------------------------
    _SALES_CACHE_TTL = 60  # seconds

    def _cache_get(self, key: str):
        """Return cached value or None if missing / expired."""
        import time
        entry = self._sales_cache.get(key)
        if entry and (time.time() - entry[0]) < self._SALES_CACHE_TTL:
            return entry[1]
        return None

    def _cache_set(self, key: str, value):
        import time
        self._sales_cache[key] = (time.time(), value)
        return value

    @staticmethod
    @lru_cache(maxsize=1)
    def _mirror_engine():
        url = (get_central_db_url() or "").strip()
        if not url:
            return None
        return create_engine(url, **get_sqlalchemy_engine_options(url))

    def _mirror_query(self, sql, params=None, expanding=None):
        engine = self._mirror_engine()
        if engine is None:
            raise RuntimeError("CENTRAL_DB_URL is not configured.")
        params = params or {}
        query = text(sql)
        for name in expanding or ():
            if name in params:
                query = query.bindparams(bindparam(name, expanding=True))
        with engine.connect() as conn:
            result = conn.execute(query, params)
            return result.mappings().all()

    _mirror_columns_cache: dict = {}

    @staticmethod
    def _mirror_columns(table_name):
        cached = ERPServiceBase._mirror_columns_cache.get(table_name)
        if cached is not None:
            return cached
        engine = ERPServiceBase._mirror_engine()
        if engine is None:
            return tuple()  # Don't cache — engine may become available later
        try:
            cols = tuple(column["name"] for column in inspect(engine).get_columns(table_name))
        except Exception:
            return tuple()  # Don't cache failures
        ERPServiceBase._mirror_columns_cache[table_name] = cols
        return cols

    @staticmethod
    def _normalize_branch_system_id(branch_id):
        """Delegate to shared branch_utils.normalize_branch."""
        return normalize_branch(branch_id)

    def _expand_branch_filters(self, branches):
        """Delegate to shared branch_utils.expand_branch_filter."""
        return expand_branch_filter(branches)

    def _mirror_so_detail_backorder_expr(self):
        columns = set(self._mirror_columns("erp_mirror_so_detail"))
        if "backordered_qty" in columns:
            return "sod.backordered_qty"
        if "bo" in columns:
            return "sod.bo"
        return "NULL"

    def _has_order_writer_column(self):
        """Check if erp_mirror_so_header has the order_writer column."""
        return "order_writer" in set(self._mirror_columns("erp_mirror_so_header"))

    def _order_writer_select(self, alias="soh"):
        """SQL expression for selecting order_writer (empty string if column missing)."""
        if self._has_order_writer_column():
            return f"MAX(COALESCE({alias}.order_writer, '')) AS order_writer"
        return "'' AS order_writer"

    def _order_writer_select_bare(self, alias=""):
        """SQL expression for selecting order_writer without alias/MAX (for non-grouped queries)."""
        prefix = f"{alias}." if alias else ""
        if self._has_order_writer_column():
            return f"COALESCE({prefix}order_writer, '') AS order_writer"
        return "'' AS order_writer"

    def _rep_filter_clause(self, alias="soh", param=":rep_id"):
        """SQL clause for filtering by rep_id on salesperson OR order_writer."""
        if self._has_order_writer_column():
            return f"(COALESCE({alias}.salesperson, '') = {param} OR COALESCE({alias}.order_writer, '') = {param})"
        return f"COALESCE({alias}.salesperson, '') = {param}"

    def _rep_filter_clause_bare(self, param=":rep_id"):
        """SQL clause for filtering by rep_id without table alias (e.g. hub_metrics)."""
        if self._has_order_writer_column():
            return f"(COALESCE(salesperson, '') = {param} OR COALESCE(order_writer, '') = {param})"
        return f"COALESCE(salesperson, '') = {param}"

    def _mirror_item_branch_qty_expr(self, alias="ib"):
        columns = set(self._mirror_columns("erp_mirror_item_branch"))
        if "qty_available" in columns:
            return f"COALESCE({alias}.qty_available, {alias}.qty_on_hand, 0)"
        if "qty_on_hand" in columns:
            return f"COALESCE({alias}.qty_on_hand, 0)"
        if "stock" in columns:
            return f"CASE WHEN COALESCE({alias}.stock, false) THEN 1 ELSE 0 END"
        return "0"

    def _require_central_db_for_cloud_mode(self):
        if not self.central_db_mode and not self.allow_legacy_erp_fallback:
            raise RuntimeError(
                "DATABASE_URL/CENTRAL_DB_URL is required for ERP mirror reads "
                "unless ENABLE_LEGACY_ERP_FALLBACK=true is explicitly enabled."
            )

    def get_connection(self):
        if not self.allow_legacy_erp_fallback:
            raise RuntimeError(
                "Legacy ERP SQL Server fallback is disabled. "
                "Set ENABLE_LEGACY_ERP_FALLBACK=true only for temporary troubleshooting."
            )
        if pyodbc is None:
            raise RuntimeError("pyodbc is not installed. Set CLOUD_MODE=True for serverless deployments.")
        last_error = None
        variants = build_sql_connection_strings()
        if not variants:
            raise RuntimeError("Missing SQL Server config. Set SQLSERVER_DSN or SQLSERVER_SERVER/SQLSERVER_DB.")

        for connection_string in variants:
            try:
                return pyodbc.connect(connection_string)
            except Exception as exc:
                last_error = exc
        raise last_error

    def _normalize_header(self, value):
        return (value or "").strip().lower().replace(" ", "").replace("_", "")

    def _load_dispatch_gps_map(self):
        if self._gps_cache is not None:
            return self._gps_cache

        path = os.environ.get('GPS_CSV_PATH')
        gps = {}
        if not path or not os.path.exists(path):
            self._gps_cache = gps
            return gps

        with open(path, 'r', encoding='utf-8', newline='') as handle:
            sample = handle.read(4096)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters="\t,;|")
            except Exception:
                dialect = csv.excel_tab if ("\t" in sample and sample.count("\t") >= sample.count(",")) else csv.excel

            reader = csv.reader(handle, dialect)
            headers = next(reader, None)
            if headers is None:
                self._gps_cache = gps
                return gps

            normalized = [self._normalize_header(h) for h in headers]

            def idx(*candidates, default=None):
                for name in candidates:
                    norm = self._normalize_header(name)
                    if norm in normalized:
                        return normalized.index(norm)
                return default

            cust_i = idx("CustomerCode", "CustCode", "Customer", default=0)
            ship_i = idx("ShipToNumber", "ShipTo", "Shipto", "ShipToSeq", default=1)
            lat_i = idx("latitude", "lat")
            lon_i = idx("longitude", "lon")
            addr_i = idx("address", "address1")
            city_i = idx("city")
            state_i = idx("state")
            zip_i = idx("zip", "postalcode", "postcode")

            for row in reader:
                if not row or len(row) <= max(cust_i, ship_i):
                    continue
                cust = str(row[cust_i]).strip()
                ship = str(row[ship_i]).strip()
                if not cust or not ship:
                    continue

                def fnum(position):
                    try:
                        if position is None or position >= len(row) or row[position] in ("", None):
                            return None
                        return float(row[position])
                    except Exception:
                        return None

                def sval(position):
                    if position is None or position >= len(row) or not row[position]:
                        return ""
                    return row[position].strip()

                parts = [v for v in [sval(addr_i), sval(city_i), sval(state_i), sval(zip_i)] if v]
                gps[(cust, ship)] = {
                    'lat': fnum(lat_i),
                    'lon': fnum(lon_i),
                    'address': " ".join(parts).strip(),
                }

        self._gps_cache = gps
        return gps

    def _get_local_pick_states(self, so_numbers=None):
        """
        Helper method to get the local pick state (Pick Printed, Picking, Picking Complete)
        for a list of SO numbers by querying the local Pick database.
        Returns a dict mapping so_number -> state.

        Uses a lightweight aggregate query instead of loading full ORM objects.
        """
        from app.Models.models import Pick
        from app.extensions import db

        # Aggregate per SO: has_active (started but not completed), has_completed
        query = db.session.query(
            Pick.barcode_number,
            func.bool_or(Pick.start_time.isnot(None) & Pick.completed_time.is_(None)).label('has_active'),
            func.bool_or(Pick.completed_time.isnot(None)).label('has_completed'),
        )
        if so_numbers:
            query = query.filter(Pick.barcode_number.in_(so_numbers))
        rows = query.group_by(Pick.barcode_number).all()

        states = {}
        for so, has_active, has_completed in rows:
            if has_active:
                states[so] = 'Picking'
            elif has_completed:
                states[so] = 'Picking Complete'
            else:
                states[so] = 'Pick Printed'
        return states

    def _get_pick_states_by_shipment(self, so_numbers=None):
        """
        Like _get_local_pick_states but keys on (so_number, shipment_num) so that
        individual shipments of the same SO can have independent pick states.
        Returns a dict mapping (so_number, shipment_num) -> state.
        Picks with no shipment_num are keyed as (so_number, None).
        """
        from app.Models.models import Pick
        from app.extensions import db

        query = db.session.query(
            Pick.barcode_number,
            Pick.shipment_num,
            func.bool_or(Pick.start_time.isnot(None) & Pick.completed_time.is_(None)).label('has_active'),
            func.bool_or(Pick.completed_time.isnot(None)).label('has_completed'),
        )
        if so_numbers:
            query = query.filter(Pick.barcode_number.in_(so_numbers))
        rows = query.group_by(Pick.barcode_number, Pick.shipment_num).all()

        states = {}
        for so, shipment, has_active, has_completed in rows:
            key = (str(so), str(shipment) if shipment else None)
            if has_active:
                states[key] = 'Picking'
            elif has_completed:
                states[key] = 'Picking Complete'
            else:
                states[key] = 'Pick Printed'
        return states

    def _get_latest_audit_event_map(self, event_type, so_numbers=None):
        """Return the latest audit timestamp for each SO for a given event type."""
        from app.Models.models import AuditEvent
        from app.extensions import db

        query = db.session.query(
            AuditEvent.so_number,
            func.max(AuditEvent.occurred_at).label('occurred_at'),
        ).filter(
            AuditEvent.event_type == event_type,
            AuditEvent.so_number.isnot(None),
        )
        if so_numbers:
            query = query.filter(AuditEvent.so_number.in_([str(so_number) for so_number in so_numbers]))

        rows = query.group_by(AuditEvent.so_number).all()
        return {str(row.so_number): row.occurred_at for row in rows}

    def _get_status_label(self, so_status, shipment_status, status_flag_delivery=None):
        """
        Centralized logic to map ERP status codes to human-readable labels.
        """
        so_s = (so_status or '').upper()
        ship_s = (shipment_status or '').upper()
        deliv_s = (status_flag_delivery or '').upper()

        if so_s == 'K': return 'PICKING'
        if so_s == 'P': return 'PARTIAL'
        if so_s == 'S':
            if deliv_s == 'E' or ship_s == 'E': return 'STAGED - EN ROUTE'
            if deliv_s == 'L' or ship_s == 'L': return 'STAGED - LOADED'
            if deliv_s == 'D' or ship_s == 'D': return 'STAGED - DELIVERED'
            return 'STAGED'
        if so_s == 'I': return 'INVOICED'
        return so_s or 'OPEN'
