import csv
import os
from datetime import date, datetime, timedelta
from functools import lru_cache

from sqlalchemy import bindparam, create_engine, func, inspect, text
from app.branch_utils import normalize_branch, expand_branch, expand_branch_filter
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

class ERPService:
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

    @staticmethod
    @lru_cache(maxsize=32)
    def _mirror_columns(table_name):
        engine = ERPService._mirror_engine()
        if engine is None:
            return tuple()
        return tuple(column["name"] for column in inspect(engine).get_columns(table_name))

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

    def _aggregate_dispatch_details(self, so_ids):
        if not so_ids:
            return {}

        if self.central_db_mode:
            columns = set(self._mirror_columns("erp_mirror_shipments_detail"))
            select_parts = ["so_id", "shipment_num"]
            if "weight" in columns:
                select_parts.append("weight")
            else:
                select_parts.append("NULL AS weight")
            for name in ("qty", "qty_ordered", "qty_shipped"):
                if name in columns:
                    select_parts.append(name)
                else:
                    select_parts.append(f"NULL AS {name}")
            rows = self._mirror_query(
                f"""
                SELECT
                    {", ".join(select_parts)}
                FROM erp_mirror_shipments_detail
                WHERE is_deleted = false
                  AND so_id IN :so_ids
                """,
                {"so_ids": [str(so_id) for so_id in so_ids]},
                expanding={"so_ids"},
            )

            aggregates = {}
            for row in rows:
                so_id = row.get("so_id")
                shipment_num = row.get("shipment_num")
                key = (so_id, shipment_num)
                info = aggregates.setdefault(key, {'item_count': 0, 'total_weight': 0.0})

                qty_value = row.get("qty_shipped")
                if (qty_value is None or float(qty_value or 0) == 0):
                    qty_value = row.get("qty_ordered")
                if (qty_value is None or float(qty_value or 0) == 0):
                    qty_value = row.get("qty")

                if qty_value is None:
                    info['item_count'] += 1
                elif float(qty_value or 0) > 0:
                    info['item_count'] += 1

                try:
                    info['total_weight'] += float(row.get("weight") or 0)
                except Exception:
                    pass

            for value in aggregates.values():
                value['total_weight'] = round(value['total_weight'], 2)
            return aggregates

        conn = self.get_connection()
        cursor = conn.cursor()
        placeholders = ",".join("?" for _ in so_ids)

        try:
            cursor.execute(f"SELECT * FROM SHIPMENTS_DETAIL WHERE so_id IN ({placeholders})", so_ids)
            rows = cursor.fetchall()
            if not rows:
                return {}

            cols = [col[0].lower() for col in cursor.description]

            def pick(*candidates):
                for candidate in candidates:
                    if candidate.lower() in cols:
                        return candidate.lower()
                return None

            so_col = pick("so_id", "soid")
            ship_col = pick("shipment_num", "shipment", "shipment_no", "release_no")
            qty_shipped_col = pick("qty_shipped", "shipped_qty", "qty_ship", "qty_delivered")
            qty_ordered_col = pick("qty_ordered", "qty", "ordered_qty", "qty_to_ship")
            weight_col = pick("weight", "line_weight", "wt")
            if not so_col:
                return {}

            index = {name: i for i, name in enumerate(cols)}
            aggregates = {}

            for row in rows:
                so_id = row[index[so_col]]
                shipment_num = row[index[ship_col]] if ship_col else None
                key = (so_id, shipment_num)
                info = aggregates.setdefault(key, {'item_count': 0, 'total_weight': 0.0})

                qty_value = None
                if qty_shipped_col:
                    qty_value = row[index[qty_shipped_col]]
                if (qty_value is None or float(qty_value or 0) == 0) and qty_ordered_col:
                    qty_value = row[index[qty_ordered_col]]

                if qty_shipped_col or qty_ordered_col:
                    if float(qty_value or 0) > 0:
                        info['item_count'] += 1
                else:
                    info['item_count'] += 1

                if weight_col:
                    try:
                        info['total_weight'] += float(row[index[weight_col]] or 0)
                    except Exception:
                        pass

            for value in aggregates.values():
                value['total_weight'] = round(value['total_weight'], 2)
            return aggregates
        finally:
            cursor.close()
            conn.close()

    def _dispatch_table_columns(self, cursor, table_name):
        cols = []
        try:
            for row in cursor.columns(table=table_name):
                cols.append(row.column_name)
        except Exception:
            return []
        return cols

    def _dispatch_pick_column(self, cols, *candidates):
        lower = {col.lower(): col for col in cols}
        for candidate in candidates:
            if candidate.lower() in lower:
                return lower[candidate.lower()]
        return None
        
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

    def get_work_orders_by_barcode(self, barcode):
        """
        Queries the ERP system for work orders associated with a Sales Order barcode.
        """
        if self.central_db_mode:
            rows = self._mirror_query(
                """
                SELECT
                    wh.wo_id,
                    wh.source_id,
                    COALESCE(i.item, sod_item.item) AS item_number,
                    COALESCE(i.description, sod_item.description) AS description,
                    wh.wo_status,
                    COALESCE(ib.handling_code, wh.department, wh.wo_rule) AS handling_code
                FROM erp_mirror_wo_header wh
                LEFT JOIN erp_mirror_so_detail sod
                    ON CAST(sod.so_id AS TEXT) = CAST(wh.source_id AS TEXT)
                   AND sod.sequence = wh.source_seq
                LEFT JOIN erp_mirror_item i
                    ON CAST(i.item_ptr AS TEXT) = CAST(wh.item_ptr AS TEXT)
                LEFT JOIN erp_mirror_item sod_item
                    ON CAST(sod_item.item_ptr AS TEXT) = CAST(sod.item_ptr AS TEXT)
                LEFT JOIN erp_mirror_item_branch ib
                    ON (
                        CAST(ib.item_ptr AS TEXT) = CAST(wh.item_ptr AS TEXT)
                        OR CAST(ib.item_ptr AS TEXT) = CAST(sod.item_ptr AS TEXT)
                    )
                   AND ib.system_id = COALESCE(wh.branch_code, sod.system_id)
                WHERE wh.is_deleted = false
                  AND CAST(wh.source_id AS TEXT) = :barcode
                  AND UPPER(COALESCE(wh.source, '')) = 'SO'
                ORDER BY wh.wo_id
                """,
                {"barcode": str(barcode)},
            )
            return [{
                'wo_number': str(row['wo_id']),
                'item_number': row['item_number'],
                'description': row['description'],
                'status': row['wo_status'],
                'handling_code': row['handling_code'],
            } for row in rows]

        self._require_central_db_for_cloud_mode()

        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Query based on User's Schema info:
            # source_id = Sales Order Number
            # wo_status = Filter (we'll fetch all for now and filter in app or refine later)
            
            query = """
                SELECT 
                    wh.wo_id, 
                    wh.source_id, 
                    i.item, 
                    i.description, 
                    wh.wo_status,
                    wh.wo_rule,
                    sod.wo_phrase
                FROM wo_header wh
                JOIN so_detail sod ON wh.source_id = sod.so_id AND wh.source_seq = sod.sequence
                JOIN item i ON sod.item_ptr = i.item_ptr
                WHERE wh.source_id = ? AND wh.source = 'SO'
            """
            
            cursor.execute(query, (barcode,))
            rows = cursor.fetchall()
            
            results = []
            if rows:
                for row in rows:
                    # Map row to dictionary
                    # Note: We need to determine which field is 'Handling Code'. 
                    # For now, we'll map 'wo_rule' or 'department' to it to see what comes back.
                    # Combine description and wo_phrase for better context
                    full_desc = row.description
                    if row.wo_phrase:
                        full_desc = f"{full_desc} - {row.wo_phrase}"

                    results.append({
                        'wo_number': str(row.wo_id), 
                        'item_number': str(row.item), 
                        'description': full_desc,
                        'status': row.wo_status,
                        'handling_code': row.wo_rule 
                    })
            else:
                 # fallback mock data if no rows found (for testing without live DB data matching)
                 pass

            conn.close()
            return results

        except Exception as e:
            print(f"ERP Connection Error: {e}")
            return []

    def get_open_picks(self):
        """
        Fetches all open picks (status 'k') from the ERP, joined with details and handling codes.
        Returns a list of dictionaries.
        """
        if self.central_db_mode:
            today = datetime.now().strftime('%Y-%m-%d')
            rows = self._mirror_query(
                """
                WITH shipment_rollup AS (
                    SELECT
                        sh.system_id,
                        CAST(sh.so_id AS TEXT) AS so_id,
                        MAX(sh.status_flag) AS status_flag,
                        MAX(sh.invoice_date) AS invoice_date,
                        MAX(sh.ship_date) AS ship_date,
                        MAX(sh.ship_via) AS ship_via,
                        MAX(sh.driver) AS driver,
                        MAX(sh.route_id_char) AS route_id_char,
                        MAX(sh.loaded_time) AS loaded_time,
                        MAX(sh.loaded_date) AS loaded_date,
                        MAX(sh.status_flag_delivery) AS status_flag_delivery
                    FROM erp_mirror_shipments_header sh
                    GROUP BY sh.system_id, CAST(sh.so_id AS TEXT)
                ),
                pick_rollup AS (
                    SELECT
                        pd.system_id,
                        CAST(pd.tran_id AS TEXT) AS so_id,
                        MAX(ph.created_date) AS created_date,
                        MAX(ph.created_time) AS created_time
                    FROM erp_mirror_pick_header ph
                    JOIN erp_mirror_pick_detail pd
                        ON ph.pick_id = pd.pick_id
                       AND ph.system_id = pd.system_id
                    WHERE ph.print_status = 'Pick Ticket'
                      AND UPPER(COALESCE(pd.tran_type, '')) = 'SO'
                    GROUP BY pd.system_id, CAST(pd.tran_id AS TEXT)
                )
                SELECT
                    soh.so_id,
                    sod.sequence,
                    i.item,
                    i.description,
                    ib.handling_code,
                    sod.qty_ordered,
                    c.cust_name,
                    cs.address_1,
                    cs.city,
                    soh.reference,
                    soh.so_status,
                    sh.status_flag,
                    soh.system_id,
                    soh.expect_date,
                    soh.sale_type,
                    sh.ship_via,
                    sh.driver,
                    sh.route_id_char AS route,
                    ph.created_time AS pick_printed_time,
                    ph.created_date AS pick_printed_date,
                    sh.loaded_time,
                    sh.loaded_date,
                    sh.ship_date,
                    sh.status_flag_delivery
                FROM erp_mirror_so_detail sod
                JOIN erp_mirror_so_header soh
                    ON soh.system_id = sod.system_id
                   AND CAST(soh.so_id AS TEXT) = CAST(sod.so_id AS TEXT)
                LEFT JOIN erp_mirror_item i
                    ON CAST(i.item_ptr AS TEXT) = CAST(sod.item_ptr AS TEXT)
                LEFT JOIN erp_mirror_item_branch ib
                    ON ib.system_id = sod.system_id
                   AND CAST(ib.item_ptr AS TEXT) = CAST(sod.item_ptr AS TEXT)
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(c.cust_key) = TRIM(soh.cust_key)
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON TRIM(cs.cust_key) = TRIM(soh.cust_key)
                   AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                LEFT JOIN shipment_rollup sh
                    ON sh.system_id = soh.system_id
                   AND sh.so_id = CAST(soh.so_id AS TEXT)
                LEFT JOIN pick_rollup ph
                    ON ph.system_id = soh.system_id
                   AND ph.so_id = CAST(soh.so_id AS TEXT)
                WHERE soh.is_deleted = false
                  AND soh.so_status != 'C'
                  AND (
                    (soh.so_status IN ('K', 'P', 'S'))
                    OR (soh.so_status = 'I' AND CAST(sh.invoice_date AS DATE) = :today)
                    OR (CAST(soh.expect_date AS DATE) = :today)
                    OR (CAST(sh.ship_date AS DATE) = :today)
                  )
                  AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
                ORDER BY soh.so_id, ib.handling_code, sod.sequence
                """,
                {"today": today},
            )

            picks = [{
                'so_number': str(row['so_id']),
                'sequence': row['sequence'],
                'item_number': row['item'],
                'description': row['description'],
                'handling_code': row['handling_code'],
                'qty': float(row['qty_ordered']) if row['qty_ordered'] is not None else 0,
                'customer_name': row['cust_name'] or 'Unknown',
                'address': f"{row['address_1']}, {row['city']}" if row['address_1'] else 'No Address',
                'reference': row['reference'],
                'so_status': row['so_status'],
                'shipment_status': row['status_flag'],
                'system_id': row['system_id'],
                'expect_date': str(row['expect_date']) if row['expect_date'] else '',
                'sale_type': row['sale_type'],
                'ship_via': row['ship_via'],
                'driver': row['driver'],
                'route': row['route'],
                'printed_at': f"{row['pick_printed_date']} {row['pick_printed_time']}" if row['pick_printed_date'] else None,
                'staged_at': f"{row['loaded_date']} {row['loaded_time']}" if row['loaded_date'] else None,
                'delivered_at': f"{row['ship_date']}" if row['ship_date'] else None,
                'status_flag_delivery': row['status_flag_delivery'],
                'line_count': 1,
            } for row in rows]

            so_numbers = [p['so_number'] for p in picks]
            local_states = self._get_local_pick_states(so_numbers)
            for pick in picks:
                pick['local_pick_state'] = local_states.get(pick['so_number'], 'Pick Printed')
            return picks

        self._require_central_db_for_cloud_mode()

        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Pulling a broader set of data for the cloud mirror:
            # 1. Open Picking/Picked/Staged (K, P, S)
            # 2. Invoiced Today (I)
            query = f"""
                SELECT 
                    soh.so_id,
                    sod.sequence,
                    i.item,
                    i.description,
                    ib.handling_code,
                sod.qty_ordered,
                c.cust_name,
                cs.address_1,
                cs.city,
                soh.reference,
                soh.so_status,
                sh.status_flag,
                soh.system_id,
                soh.expect_date,
                soh.sale_type,
                sh.ship_via,
                sh.driver,
                sh.route_id_char as route,
                ph.created_time as pick_printed_time,
                ph.created_date as pick_printed_date,
                sh.loaded_time,
                sh.loaded_date,
                sh.ship_date,
                sh.status_flag_delivery
            FROM so_detail sod
                JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id
                JOIN item i ON i.item_ptr = sod.item_ptr
                JOIN item_branch ib ON ib.item_ptr = sod.item_ptr AND sod.system_id = ib.system_id
                LEFT JOIN cust c ON soh.system_id = c.system_id AND TRY_CAST(soh.cust_key AS INT) = TRY_CAST(c.cust_key AS INT)
                LEFT JOIN cust_shipto cs ON soh.system_id = cs.system_id AND TRY_CAST(soh.cust_key AS INT) = TRY_CAST(cs.cust_key AS INT) AND TRY_CAST(soh.shipto_seq_num AS INT) = TRY_CAST(cs.seq_num AS INT)
                LEFT JOIN (
                    SELECT so_id, system_id, 
                           MAX(status_flag) as status_flag, 
                           MAX(invoice_date) as invoice_date, 
                           MAX(ship_date) as ship_date,
                           MAX(ship_via) as ship_via,
                           MAX(driver) as driver,
                           MAX(route_id_char) as route_id_char,
                           MAX(loaded_time) as loaded_time,
                           MAX(loaded_date) as loaded_date,
                           MAX(status_flag_delivery) as status_flag_delivery
                    FROM shipments_header 
                    GROUP BY so_id, system_id
                ) sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
                LEFT JOIN (
                    SELECT pd.tran_id as so_id, pd.system_id,
                           MAX(ph.created_date) as created_date,
                           MAX(ph.created_time) as created_time
                    FROM pick_header ph
                    JOIN pick_detail pd ON ph.pick_id = pd.pick_id AND ph.system_id = pd.system_id
                    WHERE ph.print_status = 'Pick Ticket' AND pd.tran_type = 'SO'
                    GROUP BY pd.tran_id, pd.system_id
                ) ph ON soh.so_id = ph.so_id AND soh.system_id = ph.system_id
                WHERE soh.so_status != 'C'
                  AND (
                    (soh.so_status IN ('K', 'P', 'S'))
                    OR (soh.so_status = 'I' AND sh.invoice_date = '{today}')
                    OR (soh.expect_date = '{today}')
                    OR (sh.ship_date = '{today}')
                  )
                  AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
                ORDER BY soh.so_id, ib.handling_code, sod.sequence
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            picks = []
            for row in rows:
                picks.append({
                    'so_number': str(row.so_id),
                    'sequence': row.sequence,
                    'item_number': row.item,
                    'description': row.description,
                    'handling_code': row.handling_code,
                    'qty': float(row.qty_ordered) if row.qty_ordered is not None else 0,
                    'customer_name': row.cust_name or 'Unknown',
                    'address': f"{row.address_1}, {row.city}" if row.address_1 else 'No Address',
                    'reference': row.reference,
                    'so_status': row.so_status,
                'shipment_status': row.status_flag,
                'system_id': row.system_id,
                'expect_date': str(row.expect_date) if row.expect_date else '',
                'sale_type': row.sale_type,
                'ship_via': row.ship_via,
                'driver': row.driver,
                'route': row.route,
                'printed_at': f"{row.pick_printed_date} {row.pick_printed_time}" if row.pick_printed_date else None,
                'staged_at': f"{row.loaded_date} {row.loaded_time}" if row.loaded_date else None,
                'delivered_at': f"{row.ship_date}" if row.ship_date else None,
                'status_flag_delivery': row.status_flag_delivery
            })
                
            conn.close()
            
            # Merge local pick states
            so_numbers = [p['so_number'] for p in picks]
            local_states = self._get_local_pick_states(so_numbers)
            
            for p in picks:
                p['local_pick_state'] = local_states.get(p['so_number'], 'Pick Printed')
                
            return picks
            
        except Exception as e:
            print(f"ERP Connection Error (Picks): {e}")
            return []

    def get_open_so_summary(self, branch=None):
        """
        Fetches a summary of Open Sales Orders (Status 'K'), grouped by Handling Code.
        Optional *branch* filters by system_id (expanded via branch_utils).
        Returns: List of dicts {so_number, customer_name, address, reference, handling_code, line_count}
        """
        cache_key = f'open_so_summary_{branch or "all"}'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        result = self._get_open_so_summary_inner(branch=branch)
        self._cache_set(cache_key, result)
        return result

    def get_open_order_board_summary(self, branch=None):
        """
        Fetches Open Sales Orders grouped at the SO level for /warehouse/board/orders.
        Returns: List of dicts {so_number, customer_name, address, reference, line_count, handling_codes}
        """
        cache_key = f'open_order_board_summary_{branch or "all"}'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        if self.central_db_mode:
            # Reuse per-handling-code summary and aggregate to SO level
            per_code = self.get_open_so_summary(branch=branch)
            so_map = {}
            for item in per_code:
                so_num = item['so_number']
                if so_num not in so_map:
                    so_map[so_num] = {
                        'so_number': so_num,
                        'customer_name': item['customer_name'],
                        'address': item['address'],
                        'reference': item['reference'],
                        'line_count': 0,
                        'handling_codes': set(),
                    }
                so_map[so_num]['line_count'] += int(item.get('line_count') or 0)
                handling_code = item.get('handling_code')
                if handling_code:
                    so_map[so_num]['handling_codes'].add(handling_code)

            summary = []
            for data in so_map.values():
                data['handling_codes'] = sorted(list(data['handling_codes']))
                summary.append(data)
        else:
            # Legacy fallback: reuse per-handling summary and aggregate in Python.
            per_code_summary = self.get_open_so_summary(branch=branch)
            so_map = {}
            for item in per_code_summary:
                so_num = item['so_number']
                if so_num not in so_map:
                    so_map[so_num] = {
                        'so_number': so_num,
                        'customer_name': item['customer_name'],
                        'address': item['address'],
                        'reference': item['reference'],
                        'line_count': 0,
                        'handling_codes': set(),
                    }
                so_map[so_num]['line_count'] += int(item.get('line_count') or 0)
                handling_code = item.get('handling_code')
                if handling_code:
                    so_map[so_num]['handling_codes'].add(handling_code)

            summary = []
            for data in so_map.values():
                data['handling_codes'] = sorted(list(data['handling_codes']))
                summary.append(data)

        so_numbers = [s['so_number'] for s in summary]
        local_states = self._get_local_pick_states(so_numbers)
        for item in summary:
            item['local_pick_state'] = local_states.get(item['so_number'], 'Pick Printed')

        self._cache_set(cache_key, summary)
        return summary

    def _get_open_so_summary_inner(self, branch=None):
        if self.central_db_mode:
            backorder_expr = self._mirror_so_detail_backorder_expr()
            filters = [
                "soh.so_status = 'K'",
                f"COALESCE({backorder_expr}, 0) = 0",
            ]
            params = {}
            expanding = set()

            # Optional branch filter — expand DSM etc.
            if branch:
                branch_ids = expand_branch(branch)
                if branch_ids:
                    filters.append("soh.system_id IN :branch_ids")
                    params["branch_ids"] = branch_ids
                    expanding.add("branch_ids")

            where_clause = " AND ".join(filters)

            rows = self._mirror_query(
                f"""
                SELECT
                    soh.so_id,
                    soh.system_id,
                    c.cust_name,
                    cs.address_1,
                    cs.city,
                    soh.reference,
                    ib.handling_code,
                    COUNT(sod.sequence) AS line_count
                FROM erp_mirror_so_detail sod
                JOIN erp_mirror_so_header soh
                    ON CAST(soh.so_id AS TEXT) = CAST(sod.so_id AS TEXT) AND sod.system_id = soh.system_id
                JOIN erp_mirror_item_branch ib
                    ON ib.item_ptr = sod.item_ptr AND sod.system_id = ib.system_id
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(c.cust_key) = TRIM(CAST(soh.cust_key AS TEXT))
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON TRIM(cs.cust_key) = TRIM(CAST(soh.cust_key AS TEXT))
                    AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                WHERE {where_clause}
                GROUP BY soh.so_id, soh.system_id, c.cust_name, cs.address_1, cs.city,
                         soh.reference, ib.handling_code
                ORDER BY ib.handling_code, soh.so_id
                """,
                params=params,
                expanding=expanding,
            )
            summary = [{
                'so_number': str(row['so_id']),
                'system_id': row['system_id'],
                'customer_name': row['cust_name'] or 'Unknown',
                'address': f"{row['address_1']}, {row['city']}" if row['address_1'] else 'No Address',
                'reference': row['reference'],
                'handling_code': row['handling_code'],
                'line_count': int(row['line_count']) if row['line_count'] is not None else 0,
            } for row in rows]

            so_numbers = [s['so_number'] for s in summary]
            local_states = self._get_local_pick_states(so_numbers)
            for item in summary:
                item['local_pick_state'] = local_states.get(item['so_number'], 'Pick Printed')
            return summary

        self._require_central_db_for_cloud_mode()

        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # User provided corrected query with cust and cust_shipto joins
            query = """
                SELECT 
                    soh.so_id,
                    c.cust_name,
                    cs.address_1,
                    cs.city,
                    soh.reference,
                    ib.handling_code,
                    COUNT(sod.sequence) as line_count
                FROM so_detail sod
                JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id
                JOIN item_branch ib ON ib.item_ptr = sod.item_ptr AND sod.system_id = ib.system_id
                LEFT JOIN cust c ON CAST(soh.cust_key AS VARCHAR) = CAST(c.cust_key AS VARCHAR) 
                JOIN cust_shipto cs ON CAST(cs.cust_key AS VARCHAR) = CAST(soh.cust_key AS VARCHAR) AND CAST(cs.seq_num AS VARCHAR) = CAST(soh.shipto_seq_num AS VARCHAR)
                WHERE soh.so_status = 'k' 
                    AND sod.bo = 0
                GROUP BY soh.so_id, c.cust_name, cs.address_1, cs.city, soh.reference, ib.handling_code
                ORDER BY ib.handling_code, soh.so_id
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            summary = []
            if rows:
                for row in rows:
                    summary.append({
                        'so_number': str(row.so_id),
                        'customer_name': row.cust_name or 'Unknown',
                        'address': f"{row.address_1}, {row.city}" if row.address_1 else 'No Address',
                        'reference': row.reference,
                        'handling_code': row.handling_code,
                        'line_count': int(row.line_count) if row.line_count is not None else 0
                    })
            
            conn.close()
            
            so_numbers = [s['so_number'] for s in summary]
            local_states = self._get_local_pick_states(so_numbers)
            
            for s in summary:
                s['local_pick_state'] = local_states.get(s['so_number'], 'Pick Printed')            
            
            return summary

        except Exception as e:
            print(f"ERP Connection Error (Open Summary): {e}")
            # print(f"ERP Connection Error (Open Summary): {e}")
            return []

    def get_historical_so_summary(self, so_numbers=None):
        """
        Fetches summary info for specific SOs (or all if None), ignoring status constraints.
        Useful for statistics and historical lookups.
        """
        if self.central_db_mode:
            backorder_expr = self._mirror_so_detail_backorder_expr()
            filters = [f"COALESCE({backorder_expr}, 0) = 0"]
            params = {}
            expanding = set()
            if so_numbers:
                filters.append("CAST(soh.so_id AS TEXT) IN :so_numbers")
                params["so_numbers"] = [str(so_number) for so_number in so_numbers]
                expanding.add("so_numbers")

            rows = self._mirror_query(
                f"""
                SELECT
                    soh.so_id,
                    c.cust_name,
                    cs.address_1,
                    cs.city,
                    soh.reference,
                    ib.handling_code,
                    COUNT(sod.sequence) AS line_count
                FROM erp_mirror_so_detail sod
                JOIN erp_mirror_so_header soh
                    ON soh.system_id = sod.system_id
                   AND CAST(soh.so_id AS TEXT) = CAST(sod.so_id AS TEXT)
                LEFT JOIN erp_mirror_item_branch ib
                    ON ib.system_id = sod.system_id
                   AND ib.item_ptr = sod.item_ptr
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(c.cust_key) = TRIM(soh.cust_key)
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON TRIM(cs.cust_key) = TRIM(soh.cust_key)
                   AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                WHERE soh.is_deleted = false AND {' AND '.join(filters)}
                GROUP BY soh.so_id, c.cust_name, cs.address_1, cs.city, soh.reference, ib.handling_code
                """,
                params,
                expanding=expanding,
            )
            return [{
                'so_number': str(row['so_id']),
                'customer_name': row['cust_name'] or 'Unknown',
                'address': f"{row['address_1']}, {row['city']}" if row['address_1'] else 'No Address',
                'reference': row['reference'],
                'handling_code': row['handling_code'],
                'line_count': int(row['line_count']) if row['line_count'] is not None else 0,
            } for row in rows]

        self._require_central_db_for_cloud_mode()

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            base_query = """
                SELECT 
                    soh.so_id,
                    c.cust_name,
                    cs.address_1,
                    cs.city,
                    soh.reference,
                    ib.handling_code,
                    COUNT(sod.sequence) as line_count
                FROM so_detail sod
                JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id
                JOIN item_branch ib ON ib.item_ptr = sod.item_ptr AND sod.system_id = ib.system_id
                LEFT JOIN cust c ON CAST(soh.cust_key AS VARCHAR) = CAST(c.cust_key AS VARCHAR) 
                JOIN cust_shipto cs ON CAST(cs.cust_key AS VARCHAR) = CAST(soh.cust_key AS VARCHAR) AND CAST(cs.seq_num AS VARCHAR) = CAST(soh.shipto_seq_num AS VARCHAR)
                WHERE sod.bo = 0
            """
            
            if so_numbers:
                # Chunking to avoid SQL variable limits
                chunk_size = 900
                summary = []
                for i in range(0, len(so_numbers), chunk_size):
                    chunk = so_numbers[i:i + chunk_size]
                    placeholders = ', '.join(['?' for _ in chunk])
                    query = base_query + f" AND soh.so_id IN ({placeholders})"
                    query += " GROUP BY soh.so_id, c.cust_name, cs.address_1, cs.city, soh.reference, ib.handling_code"
                    cursor.execute(query, tuple(chunk))
                    rows = cursor.fetchall()
                    for row in rows:
                        summary.append({
                            'so_number': str(row.so_id),
                            'customer_name': row.cust_name or 'Unknown',
                            'address': f"{row.address_1}, {row.city}" if row.address_1 else 'No Address',
                            'reference': row.reference,
                            'handling_code': row.handling_code,
                            'line_count': row.line_count
                        })
                conn.close()
                return summary
            else:
                query = base_query + " GROUP BY soh.so_id, c.cust_name, cs.address_1, cs.city, soh.reference, ib.handling_code"
                cursor.execute(query)
                rows = cursor.fetchall()
                summary = []
                for row in rows:
                    summary.append({
                        'so_number': str(row.so_id),
                        'customer_name': row.cust_name or 'Unknown',
                        'address': f"{row.address_1}, {row.city}" if row.address_1 else 'No Address',
                        'reference': row.reference,
                        'handling_code': row.handling_code,
                        'line_count': row.line_count
                    })
            
            conn.close()
            return summary
        except Exception as e:
            print(f"ERP Connection Error (Hist Summary): {e}")
            return []

    def get_so_header(self, so_number):
        """
        Fetches header info (Customer, Reference, etc.) for a single Sales Order.
        """
        if self.central_db_mode:
            rows = self._mirror_query(
                """
                SELECT
                    soh.so_id,
                    c.cust_name,
                    cs.address_1,
                    cs.city,
                    soh.reference,
                    soh.system_id,
                    COALESCE(sh.ship_via, soh.ship_via) AS ship_via,
                    sh.driver,
                    sh.route_id_char AS route,
                    sh.loaded_date,
                    sh.loaded_time,
                    sh.ship_date,
                    sh.status_flag_delivery
                FROM erp_mirror_so_header soh
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(CAST(c.cust_key AS TEXT)) = TRIM(CAST(soh.cust_key AS TEXT))
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON TRIM(CAST(cs.cust_key AS TEXT)) = TRIM(CAST(soh.cust_key AS TEXT))
                    AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                LEFT JOIN erp_mirror_shipments_header sh
                    ON sh.system_id = soh.system_id AND CAST(sh.so_id AS TEXT) = CAST(soh.so_id AS TEXT)
                WHERE soh.is_deleted = false
                  AND CAST(soh.so_id AS TEXT) = :so_number
                ORDER BY sh.ship_date DESC NULLS LAST, sh.invoice_date DESC NULLS LAST
                LIMIT 1
                """,
                {"so_number": str(so_number)},
            )
            row = rows[0] if rows else None
            if not row:
                return None
            staged_events = self._get_latest_audit_event_map('staged_confirmed', [so_number])
            staged_at = f"{row['loaded_date']} {row['loaded_time']}" if row['loaded_date'] else None
            if not staged_at:
                staged_at = staged_events.get(str(so_number))
            return {
                'so_number': str(row['so_id']),
                'customer_name': row['cust_name'] or 'Unknown',
                'address': f"{row['address_1']}, {row['city']}" if row['address_1'] else 'No Address',
                'reference': row['reference'],
                'system_id': row['system_id'],
                'ship_via': row['ship_via'],
                'driver': row['driver'],
                'route': row['route'],
                'status_flag': row['status_flag_delivery'],
                'printed_at': None,
                'staged_at': staged_at,
                'delivered_at': row['ship_date'] if row['status_flag_delivery'] == 'D' else None,
            }
        self._require_central_db_for_cloud_mode()

        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            query = """
                SELECT TOP 1
                    soh.so_id,
                    c.cust_name,
                    cs.address_1,
                    cs.city,
                    soh.reference,
                    soh.system_id,
                    sh.ship_via,
                    sh.driver,
                    sh.route_id_char as route,
                    sh.loaded_date,
                    sh.loaded_time,
                    sh.ship_date,
                    sh.status_flag,
                    ph.created_time as printed_at
                FROM so_header soh
                LEFT JOIN cust c ON CAST(soh.cust_key AS VARCHAR) = CAST(c.cust_key AS VARCHAR)
                JOIN cust_shipto cs ON CAST(cs.cust_key AS VARCHAR) = CAST(soh.cust_key AS VARCHAR) AND CAST(cs.seq_num AS VARCHAR) = CAST(soh.shipto_seq_num AS VARCHAR)
                LEFT JOIN shipments_header sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
                LEFT JOIN pick_header ph ON soh.so_id = ph.so_id AND soh.system_id = ph.system_id AND ph.print_status = 'Pick Ticket'
                WHERE soh.so_id = ?
            """
            cursor.execute(query, (so_number,))
            row = cursor.fetchone()
            
            header = None
            if row:
                staged_events = self._get_latest_audit_event_map('staged_confirmed', [so_number])
                staged_at = f"{row.loaded_date} {row.loaded_time}" if row.loaded_date else None
                if not staged_at:
                    staged_at = staged_events.get(str(so_number))
                header = {
                    'so_number': str(row.so_id),
                    'customer_name': row.cust_name or 'Unknown',
                    'address': f"{row.address_1}, {row.city}" if row.address_1 else 'No Address',
                    'reference': row.reference,
                    'system_id': row.system_id,
                    'ship_via': row.ship_via,
                    'driver': row.driver,
                    'route': row.route,
                    'status_flag': row.status_flag,
                    'printed_at': row.printed_at,
                    'staged_at': staged_at,
                    'delivered_at': row.ship_date if row.status_flag == 'D' else None
                }
            
            conn.close()
            return header
        except Exception as e:
            print(f"ERP Connection Error (SO Header): {e}")
            return None

    def get_so_details(self, so_number):
        """
        Fetches all line items for a specific Sales Order.
        """
        if self.central_db_mode:
            rows = self._mirror_query(
                """
                SELECT
                    sod.so_id,
                    sod.sequence,
                    i.item,
                    i.description,
                    ib.handling_code,
                    sod.qty_ordered
                FROM erp_mirror_so_detail sod
                LEFT JOIN erp_mirror_item i
                    ON i.item_ptr = sod.item_ptr
                LEFT JOIN erp_mirror_item_branch ib
                    ON ib.system_id = sod.system_id AND ib.item_ptr = sod.item_ptr
                WHERE CAST(sod.so_id AS TEXT) = :so_number
                ORDER BY ib.handling_code NULLS LAST, sod.sequence
                """,
                {"so_number": str(so_number)},
            )
            return [{
                'so_number': str(row['so_id']),
                'sequence': row['sequence'],
                'item_number': row['item'],
                'description': row['description'],
                'handling_code': row['handling_code'],
                'qty': row['qty_ordered'],
            } for row in rows]
        self._require_central_db_for_cloud_mode()

        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            query = """
                SELECT
                    soh.so_id,
                    sod.sequence,
                    i.item,
                    i.description,
                    ib.handling_code,
                    sod.qty_ordered
                FROM so_detail sod
                JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id
                JOIN item i ON i.item_ptr = sod.item_ptr
                JOIN item_branch ib ON ib.item_ptr = sod.item_ptr AND sod.system_id = ib.system_id
                WHERE soh.so_id = ?
                ORDER BY ib.handling_code, sod.sequence
            """
            
            cursor.execute(query, (so_number,))
            rows = cursor.fetchall()
            
            items = []
            for row in rows:
                 items.append({
                    'so_number': str(row.so_id),
                    'sequence': row.sequence,
                    'item_number': row.item,
                    'description': row.description,
                    'handling_code': row.handling_code,
                    'qty': row.qty_ordered
                })
            
            conn.close()
            return items

        except Exception as e:
            print(f"ERP Connection Error (Detail): {e}")
            return []

    def get_dispatch_stops(
        self,
        start: date,
        end: date,
        sale_types=None,
        status_filter=None,
        route_id=None,
        driver=None,
        include_no_gps=False,
        branches=None,
    ):
        if self.central_db_mode:
            filters = [
                "soh.is_deleted = false",
                "("
                " (UPPER(COALESCE(soh.sale_type, '')) = 'CM' AND UPPER(COALESCE(soh.so_status, '')) NOT IN ('I','C','X','CAN','CANCEL','CANCELED','CN','VOID'))"
                " OR "
                " (UPPER(COALESCE(soh.sale_type, '')) <> 'CM' AND COALESCE(sh.expect_date, soh.expect_date) BETWEEN :start_date AND :end_date)"
                ")",
                "UPPER(COALESCE(soh.so_status,'')) NOT IN ('I','C','X','CAN','CANCEL','CANCELED','CN','VOID')",
                "UPPER(COALESCE(soh.sale_type,'')) NOT IN ('DIRECT','WILLCALL','HOLD')",
            ]
            params = {"start_date": start, "end_date": end}

            expanded = self._expand_branch_filters(branches)
            if expanded:
                filters.append("soh.system_id IN :branches")
                params["branches"] = expanded

            if sale_types:
                types = [item.strip() for item in sale_types.split(",") if item.strip()]
                if types:
                    filters.append("soh.sale_type IN :sale_types")
                    params["sale_types"] = types

            if status_filter:
                statuses = [item.strip().upper() for item in status_filter.split(",") if item.strip()]
                if statuses:
                    filters.append("soh.so_status IN :statuses")
                    params["statuses"] = statuses

            if route_id:
                filters.append("COALESCE(sh.route_id_char, soh.branch_code) = :route_id")
                params["route_id"] = route_id

            if driver:
                filters.append("sh.driver = :driver")
                params["driver"] = driver

            rows = self._mirror_query(
                f"""
                SELECT
                    soh.so_id AS id,
                    CASE WHEN UPPER(COALESCE(soh.sale_type, '')) = 'CM' THEN 'credit' ELSE 'delivery' END AS doc_kind,
                    COALESCE(sh.expect_date, soh.expect_date) AS expected_date,
                    cs.lat,
                    cs.lon,
                    NULL AS address,
                    soh.so_status,
                    CASE WHEN UPPER(COALESCE(soh.sale_type, '')) = 'CM' THEN 'CM' ELSE 'SO' END AS so_type,
                    COALESCE(cs.shipto_name, c.cust_name) AS shipto_name,
                    CONCAT_WS(' ', cs.address_1, cs.city, cs.state, cs.zip) AS shipto_address,
                    c.cust_name AS customer_name,
                    c.cust_code AS customer_code,
                    CAST(soh.shipto_seq_num AS TEXT) AS ship_to_number,
                    sh.shipment_num,
                    sh.route_id_char AS route_id,
                    sh.driver,
                    soh.system_id AS branch
                FROM erp_mirror_so_header soh
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(CAST(c.cust_key AS TEXT)) = TRIM(CAST(soh.cust_key AS TEXT))
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON TRIM(CAST(cs.cust_key AS TEXT)) = TRIM(CAST(soh.cust_key AS TEXT))
                    AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                LEFT JOIN erp_mirror_shipments_header sh
                    ON sh.system_id = soh.system_id AND CAST(sh.so_id AS TEXT) = CAST(soh.so_id AS TEXT)
                WHERE {' AND '.join(filters)}
                ORDER BY COALESCE(sh.expect_date, soh.expect_date), soh.so_id
                """,
                params,
                expanding={"branches", "sale_types", "statuses"},
            )

            so_ids = [row["id"] for row in rows if row.get("id") is not None]
            aggregates = self._aggregate_dispatch_details(so_ids) if so_ids else {}

            results = []
            for row in rows:
                obj = dict(row)
                for text_key in ("shipto_name", "customer_name", "shipto_address", "address"):
                    value = obj.get(text_key)
                    if isinstance(value, str):
                        obj[text_key] = value.strip()
                # Coerce Decimal lat/lon from DB to float
                if obj.get("lat") is not None:
                    obj["lat"] = float(obj["lat"])
                if obj.get("lon") is not None:
                    obj["lon"] = float(obj["lon"])
                # Use DB ship-to/customer values even when GPS is still unresolved
                if not obj.get("shipto_name") and obj.get("customer_name"):
                    obj["shipto_name"] = obj["customer_name"]
                if not obj.get("customer_name"):
                    obj["customer_name"] = "Unknown Customer"
                if not obj.get("shipto_name"):
                    obj["shipto_name"] = obj["customer_name"]
                if not obj.get("address") and obj.get("shipto_address"):
                    obj["address"] = obj["shipto_address"]
                obj.pop("shipto_address", None)
                if not include_no_gps and (obj.get("lat") is None or obj.get("lon") is None):
                    continue
                info = aggregates.get((obj.get("id"), obj.get("shipment_num"))) or aggregates.get((obj.get("id"), None))
                if info:
                    obj["item_count"] = info.get("item_count")
                    obj["total_weight"] = info.get("total_weight")
                obj.pop("customer_code", None)
                obj.pop("ship_to_number", None)
                if hasattr(obj.get("expected_date"), "isoformat"):
                    obj["expected_date"] = obj["expected_date"].isoformat()
                results.append(obj)
            return results
        self._require_central_db_for_cloud_mode()

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            filters = [
                "("
                " (UPPER(hdr.[type]) = 'CM' AND UPPER(hdr.so_status) NOT IN ('I','C','X','CAN','CANCEL','CANCELED','CN','VOID'))"
                " OR "
                " (UPPER(hdr.[type]) <> 'CM' AND COALESCE(sh.expect_date, hdr.expect_date) BETWEEN ? AND ?)"
                ")",
                "UPPER(hdr.so_status) NOT IN ('I','C','X','CAN','CANCEL','CANCELED','CN','VOID')",
                "UPPER(COALESCE(hdr.sale_type,'')) NOT IN ('DIRECT','WILLCALL','HOLD')",
            ]
            params = [start, end]

            if sale_types:
                types = [item.strip() for item in sale_types.split(",") if item.strip()]
                if types:
                    filters.append(f"hdr.sale_type IN ({','.join('?' for _ in types)})")
                    params.extend(types)

            if status_filter:
                statuses = [item.strip() for item in status_filter.split(",") if item.strip()]
                if statuses:
                    filters.append(f"hdr.so_status IN ({','.join('?' for _ in statuses)})")
                    params.extend(statuses)

            if route_id:
                filters.append("COALESCE(sh.route_id_char, hdr.route_id_char) = ?")
                params.append(route_id)

            if driver:
                filters.append("COALESCE(sh.driver, hdr.driver) = ?")
                params.append(driver)

            if branches:
                expanded = expand_branch_filter(branches)
                if expanded:
                    filters.append(f"hdr.system_id IN ({','.join('?' for _ in expanded)})")
                    params.extend(expanded)

            query = f"""
            WITH Stops AS (
                SELECT
                    hdr.so_id AS id,
                    CASE WHEN UPPER(hdr.[type]) = 'CM' THEN 'credit' ELSE 'delivery' END AS doc_kind,
                    COALESCE(sh.expect_date, hdr.expect_date) AS expected_date,
                    CAST(NULL AS decimal(9,6)) AS lat,
                    CAST(NULL AS decimal(9,6)) AS lon,
                    CAST(NULL AS nvarchar(200)) AS address,
                    hdr.so_status,
                    hdr.[type] AS so_type,
                    COALESCE(st.shipto_name, cust.cust_name) AS shipto_name,
                    CONCAT_WS(' ', st.address_1, st.city, st.state, st.zip) AS shipto_address,
                    cust.cust_name AS customer_name,
                    cust.cust_code AS CustomerCode,
                    CAST(hdr.shipto_seq_num AS nvarchar(32)) AS ShipToNumber,
                    sh.shipment_num AS shipment_num,
                    COALESCE(sh.route_id_char, hdr.route_id_char) AS route_id,
                    COALESCE(sh.driver, hdr.driver) AS driver,
                    hdr.system_id AS branch
                FROM SO_HEADER hdr
                LEFT JOIN CUST_SHIPTO st
                    ON hdr.system_id = st.system_id
                    AND CAST(st.cust_key AS nvarchar(64)) = CAST(hdr.cust_key AS nvarchar(64))
                    AND CAST(st.seq_num AS nvarchar(32)) = CAST(hdr.shipto_seq_num AS nvarchar(32))
                LEFT JOIN SHIPMENTS_HEADER sh ON sh.so_id = hdr.so_id AND sh.system_id = hdr.system_id
                LEFT JOIN CUST cust ON cust.system_id = hdr.system_id AND cust.cust_key = hdr.cust_key
                WHERE {" AND ".join(filters)}
            )
            SELECT
                id, doc_kind, expected_date, lat, lon, address,
                so_status, so_type, shipto_name, shipto_address, customer_name,
                shipment_num, route_id, driver, branch,
                CustomerCode, ShipToNumber
            FROM Stops
            ORDER BY expected_date, id
            """

            cursor.execute(query, params)
            rows = cursor.fetchall()
            cols = [col[0] for col in cursor.description]
        finally:
            cursor.close()
            conn.close()

        results = []
        for row in rows:
            obj = dict(zip(cols, row))
            if hasattr(obj.get("expected_date"), "isoformat"):
                obj["expected_date"] = obj["expected_date"].isoformat()
            results.append(obj)

        gps_map = self._load_dispatch_gps_map()
        for obj in results:
            if not obj.get("shipto_name") and obj.get("customer_name"):
                obj["shipto_name"] = obj["customer_name"]
            if not obj.get("address") and obj.get("shipto_address"):
                obj["address"] = obj["shipto_address"]
            customer = (obj.get("CustomerCode") or "").strip()
            ship_to = (obj.get("ShipToNumber") or "").strip()
            hit = gps_map.get((customer, ship_to))
            if hit and hit.get('lat') is not None and hit.get('lon') is not None:
                obj['lat'] = hit['lat']
                obj['lon'] = hit['lon']
                if not obj.get('address'):
                    obj['address'] = hit.get('address')
                obj['gps_status'] = 'csv_unverified'
                obj['gps_verified'] = False
            else:
                obj['gps_status'] = 'missing'
                obj['gps_verified'] = False

        for obj in results:
            obj.pop('CustomerCode', None)
            obj.pop('ShipToNumber', None)
            obj.pop('shipto_address', None)

        if not include_no_gps:
            results = [item for item in results if item.get('lat') is not None and item.get('lon') is not None]

        try:
            so_ids = [item.get('id') for item in results if item.get('id') is not None]
            aggregates = self._aggregate_dispatch_details(so_ids)
            for item in results:
                key = (item.get('id'), item.get('shipment_num'))
                info = aggregates.get(key) or aggregates.get((item.get('id'), None))
                if info:
                    item['item_count'] = info.get('item_count')
                    item['total_weight'] = info.get('total_weight')
        except Exception:
            pass

        return results

    def get_dispatch_shipment_lines(self, so_id, shipment_num=None, limit=200):
        if self.central_db_mode:
            columns = set(self._mirror_columns("erp_mirror_shipments_detail"))
            line_expr = "line_no"
            if "line_no" not in columns:
                if "sequence" in columns:
                    line_expr = "sequence"
                else:
                    line_expr = "NULL"
            qty_expr = "NULL"
            if "qty_ordered" in columns and "qty" in columns:
                qty_expr = "COALESCE(qty_ordered, qty)"
            elif "qty_ordered" in columns:
                qty_expr = "qty_ordered"
            elif "qty" in columns:
                qty_expr = "qty"

            shipped_expr = qty_expr
            if "qty_shipped" in columns:
                shipped_expr = f"COALESCE(qty_shipped, {qty_expr})"

            weight_expr = "weight" if "weight" in columns else "NULL AS weight"
            params = {"so_id": str(so_id), "limit": limit}
            where = "CAST(so_id AS TEXT) = :so_id"
            if shipment_num is not None:
                where += " AND CAST(shipment_num AS TEXT) = :shipment_num"
                params["shipment_num"] = str(shipment_num)
            rows = self._mirror_query(
                f"""
                SELECT
                    so_id,
                    shipment_num,
                    {line_expr} AS line_no,
                    {"item_ptr" if "item_ptr" in columns else "NULL"} AS item_id,
                    NULL AS item_description,
                    {qty_expr} AS qty_ordered,
                    {shipped_expr} AS qty_shipped,
                    NULL AS uom,
                    {weight_expr}
                FROM erp_mirror_shipments_detail
                WHERE is_deleted = false AND {where}
                ORDER BY line_no
                LIMIT :limit
                """,
                params,
            )
            return [
                {
                    **dict(row),
                    "address": ", ".join(part for part in [row.get("address_1"), row.get("city")] if part),
                }
                for row in rows
            ]
        self._require_central_db_for_cloud_mode()

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cols = self._dispatch_table_columns(cursor, "SHIPMENTS_DETAIL")
            if not cols:
                return []

            so_col = self._dispatch_pick_column(cols, "so_id", "soid", "so") or "so_id"
            shipment_col = self._dispatch_pick_column(cols, "shipment_num", "shipment_id", "release_no", "shipment_no")
            line_col = self._dispatch_pick_column(cols, "line_no", "line", "seq", "sequence", "detail_seq")
            item_col = self._dispatch_pick_column(cols, "item_id", "item_no", "sku", "merch_id", "prod_id")
            desc_col = self._dispatch_pick_column(cols, "item_description", "description", "item_desc", "descr")
            qty_ordered_col = self._dispatch_pick_column(cols, "qty_ordered", "qty", "ordered_qty", "qty_to_ship")
            qty_shipped_col = self._dispatch_pick_column(cols, "qty_shipped", "shipped_qty", "qty_ship", "qty_delivered")
            uom_col = self._dispatch_pick_column(cols, "uom", "unit", "unit_of_measure")
            weight_col = self._dispatch_pick_column(cols, "weight", "line_weight", "wt")

            select_parts = [f"{so_col} AS so_id"]
            if shipment_col:
                select_parts.append(f"{shipment_col} AS shipment_num")
            if line_col:
                select_parts.append(f"{line_col} AS line_no")
            if item_col:
                select_parts.append(f"{item_col} AS item_id")
            if desc_col:
                select_parts.append(f"{desc_col} AS item_description")
            if qty_ordered_col:
                select_parts.append(f"{qty_ordered_col} AS qty_ordered")
            if qty_shipped_col:
                select_parts.append(f"{qty_shipped_col} AS qty_shipped")
            if uom_col:
                select_parts.append(f"{uom_col} AS uom")
            if weight_col:
                select_parts.append(f"{weight_col} AS weight")

            order_by = line_col or item_col or shipment_col or so_col
            where = f"{so_col} = ?"
            params = [so_id]
            if shipment_num is not None and shipment_col:
                where += f" AND {shipment_col} = ?"
                params.append(shipment_num)

            query = f"SELECT {', '.join(select_parts)} FROM SHIPMENTS_DETAIL WHERE {where} ORDER BY {order_by}"
            cursor.execute(query, params)
            names = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(names, row)) for row in rows][:limit]
        finally:
            cursor.close()
            conn.close()

    def get_delivery_orders(self):
        """
        Fetches open Sales Orders that are ready for delivery (status 'K').
        Returns a list of dicts with SO header info plus line counts, suitable for the delivery board.
        This reuses the open SO summary but could be refined to filter by delivery-specific handling codes.
        """
        if self.central_db_mode:
            backorder_expr = self._mirror_so_detail_backorder_expr()
            rows = self._mirror_query(
                f"""
                SELECT
                    soh.so_id,
                    c.cust_name,
                    cs.address_1,
                    cs.city,
                    soh.reference,
                    soh.system_id,
                    COUNT(sod.sequence) AS line_count,
                    MAX(sh.ship_via) AS ship_via,
                    MAX(sh.driver) AS driver,
                    MAX(sh.route_id_char) AS route
                FROM erp_mirror_so_detail sod
                JOIN erp_mirror_so_header soh
                    ON soh.system_id = sod.system_id AND CAST(soh.so_id AS TEXT) = CAST(sod.so_id AS TEXT)
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(c.cust_key) = TRIM(soh.cust_key)
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON TRIM(cs.cust_key) = TRIM(soh.cust_key) AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                LEFT JOIN erp_mirror_shipments_header sh
                    ON sh.system_id = soh.system_id AND CAST(sh.so_id AS TEXT) = CAST(soh.so_id AS TEXT)
                WHERE soh.is_deleted = false
                  AND UPPER(COALESCE(soh.so_status, '')) = 'K'
                  AND COALESCE({backorder_expr}, 0) = 0
                GROUP BY soh.so_id, c.cust_name, cs.address_1, cs.city, soh.reference, soh.system_id
                ORDER BY soh.so_id
                """
            )
            return [{
                'so_number': str(row['so_id']),
                'customer_name': row['cust_name'] or 'Unknown',
                'address': f"{row['address_1']}, {row['city']}" if row['address_1'] else 'No Address',
                'reference': row['reference'],
                'system_id': row['system_id'],
                'line_count': row['line_count'],
                'ship_via': row['ship_via'],
                'driver': row['driver'],
                'route': row['route'],
            } for row in rows]
        self._require_central_db_for_cloud_mode()

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            query = """
                SELECT
                    soh.so_id,
                    c.cust_name,
                    cs.address_1,
                    cs.city,
                    soh.reference,
                    soh.system_id,
                    COUNT(sod.sequence) as line_count,
                    MAX(sh.ship_via) as ship_via,
                    MAX(sh.driver) as driver,
                    MAX(sh.route_id_char) as route
                FROM so_detail sod
                JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id
                LEFT JOIN cust c ON CAST(soh.cust_key AS VARCHAR) = CAST(c.cust_key AS VARCHAR)
                JOIN cust_shipto cs ON CAST(cs.cust_key AS VARCHAR) = CAST(soh.cust_key AS VARCHAR) AND CAST(cs.seq_num AS VARCHAR) = CAST(soh.shipto_seq_num AS VARCHAR)
                LEFT JOIN shipments_header sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
                WHERE soh.so_status = 'k'
                    AND sod.bo = 0
                GROUP BY soh.so_id, c.cust_name, cs.address_1, cs.city, soh.reference, soh.system_id
                ORDER BY soh.so_id
            """

            cursor.execute(query)
            rows = cursor.fetchall()

            orders = []
            for row in rows:
                orders.append({
                    'so_number': str(row.so_id),
                    'customer_name': row.cust_name or 'Unknown',
                    'address': f"{row.address_1}, {row.city}" if row.address_1 else 'No Address',
                    'reference': row.reference,
                    'system_id': row.system_id,
                    'line_count': row.line_count,
                    'ship_via': row.ship_via,
                    'driver': row.driver,
                    'route': row.route
                })

            conn.close()
            return orders

        except Exception as e:
            print(f"ERP Connection Error (Delivery Orders): {e}")
            return []

    def get_sales_hub_metrics(self):
        cached = self._cache_get('hub_metrics')
        if cached is not None:
            return cached
        result = self._get_sales_hub_metrics_inner()
        return self._cache_set('hub_metrics', result)

    def _get_sales_hub_metrics_inner(self):
        if self.central_db_mode:
            today = date.today().isoformat()
            rows = self._mirror_query(
                """
                SELECT
                    COUNT(DISTINCT CASE WHEN UPPER(COALESCE(so_status, '')) = 'O' THEN so_id END) AS open_orders_count,
                    COUNT(DISTINCT CASE WHEN CAST(expect_date AS DATE) = :today THEN so_id END) AS total_orders_today
                FROM erp_mirror_so_header
                WHERE is_deleted = false
                """,
                {"today": today},
            )
            row = rows[0] if rows else {}
            return {
                "open_orders_count": int(row.get("open_orders_count") or 0),
                "total_orders_today": int(row.get("total_orders_today") or 0),
            }

        self._require_central_db_for_cloud_mode()
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            today = datetime.today().strftime('%Y-%m-%d')
            # Note: SQL Server queries so_header directly (not the mirror tables), which does
            # not have an is_deleted column. Soft-delete filtering is only applied on the
            # PostgreSQL mirror tables (erp_mirror_so_header). This is intentional.
            cursor.execute(
                """
                SELECT
                    COUNT(DISTINCT CASE WHEN UPPER(COALESCE(so_status, '')) = 'O' THEN so_id END) AS open_orders_count,
                    COUNT(DISTINCT CASE WHEN CAST(expect_date AS DATE) = ? THEN so_id END) AS total_orders_today
                FROM so_header
                """,
                (today,),
            )
            row = cursor.fetchone()
            return {
                "open_orders_count": int(getattr(row, "open_orders_count", 0) or 0),
                "total_orders_today": int(getattr(row, "total_orders_today", 0) or 0),
            }
        finally:
            cursor.close()
            conn.close()

    def get_sales_rep_metrics(self, period_days=30):
        cache_key = f'rep_metrics_{period_days}'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        result = self._get_sales_rep_metrics_inner(period_days=period_days)
        self._cache_set(cache_key, result)
        return result

    def _get_sales_rep_metrics_inner(self, period_days=30):
        if self.central_db_mode:
            since = datetime.utcnow() - timedelta(days=period_days)
            rows = self._mirror_query(
                """
                SELECT
                    COUNT(DISTINCT COALESCE(c.cust_key, soh.cust_key)) AS active_customers,
                    COALESCE(SUM(sod.qty_ordered * sod.price), 0) AS open_orders_value
                FROM erp_mirror_so_header soh
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(c.cust_key) = TRIM(soh.cust_key)
                LEFT JOIN erp_mirror_so_detail sod
                    ON sod.system_id = soh.system_id AND CAST(sod.so_id AS TEXT) = CAST(soh.so_id AS TEXT)
                WHERE soh.is_deleted = false
                  AND COALESCE(soh.expect_date, soh.source_updated_at, soh.synced_at) >= :since
                  AND UPPER(COALESCE(soh.so_status, '')) = 'O'
                """,
                {"since": since},
            )
            row = rows[0] if rows else {}
            open_orders_value = float(row.get("open_orders_value") or 0)
            monthly_goal_progress = min(int(open_orders_value / 200000 * 100), 100)
            return {
                "active_customers": int(row.get("active_customers") or 0),
                "open_orders_value": open_orders_value,
                "monthly_goal_progress": monthly_goal_progress,
            }

        self._require_central_db_for_cloud_mode()
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            since = datetime.utcnow() - timedelta(days=period_days)
            cursor.execute(
                """
                SELECT
                    COUNT(DISTINCT CAST(soh.cust_key AS VARCHAR(255))) AS active_customers,
                    COALESCE(SUM(sod.qty_ordered * sod.price), 0) AS open_orders_value
                FROM so_header soh
                LEFT JOIN so_detail sod
                    ON sod.system_id = soh.system_id AND sod.so_id = soh.so_id
                WHERE COALESCE(soh.expect_date, soh.invoice_date, soh.created_date) >= ?
                AND UPPER(COALESCE(soh.so_status, '')) = 'O'
                """,
                (since,),
            )
            row = cursor.fetchone()
            open_orders_value = float(getattr(row, "open_orders_value", 0) or 0)
            monthly_goal_progress = min(int(open_orders_value / 200000 * 100), 100)
            return {
                "active_customers": int(getattr(row, "active_customers", 0) or 0),
                "open_orders_value": open_orders_value,
                "monthly_goal_progress": monthly_goal_progress,
            }
        finally:
            cursor.close()
            conn.close()

    def get_sales_order_status(self, q="", limit=100, branch="", open_only=True):
        # Cache unfiltered list for 60 s; skip cache for searches, branch filters, or all-status mode
        cache_key = f'order_status_{limit}' if not q and not branch and open_only else None
        if cache_key:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached
        result = self._get_sales_order_status_inner(q=q, limit=limit, branch=branch, open_only=open_only)
        if cache_key:
            self._cache_set(cache_key, result)
        return result

    def _get_sales_order_status_inner(self, q="", limit=100, branch="", open_only=True):
        if self.central_db_mode:
            sod_columns = set(self._mirror_columns("erp_mirror_so_detail"))
            if "line_no" in sod_columns:
                line_count_expr = "COUNT(DISTINCT sod.line_no) AS line_count"
            elif "sequence" in sod_columns:
                line_count_expr = "COUNT(DISTINCT sod.sequence) AS line_count"
            else:
                line_count_expr = "COUNT(sod.id) AS line_count"
            params = {"limit": limit}
            clauses = ["soh.is_deleted = false"]
            if open_only:
                clauses.append("soh.so_status = 'O'")
            if q:
                params["q"] = f"%{q}%"
                clauses.append(
                    "(soh.so_id::text ILIKE :q"
                    " OR COALESCE(c.cust_name, '') ILIKE :q"
                    " OR COALESCE(c.cust_code, '') ILIKE :q)"
                )
            if branch:
                system_id = self._normalize_branch_system_id(branch)
                if system_id:
                    params["branch_id"] = system_id
                    clauses.append("soh.system_id = :branch_id")
            where_clause = "WHERE " + " AND ".join(clauses)
            rows = self._mirror_query(
                f"""
                SELECT
                    soh.so_id::text AS so_number,
                    MAX(c.cust_name) AS customer_name,
                    MAX(c.cust_code) AS customer_code,
                    MAX(cs.address_1) AS address_1,
                    MAX(cs.city) AS city,
                    MAX(soh.expect_date) AS expect_date,
                    MAX(soh.reference) AS reference,
                    MAX(soh.so_status) AS so_status,
                    MAX(soh.synced_at) AS synced_at,
                    '' AS handling_code,
                    MAX(soh.sale_type) AS sale_type,
                    MAX(COALESCE(soh.ship_via, '')) AS ship_via,
                    {line_count_expr}
                FROM erp_mirror_so_header soh
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(c.cust_key) = TRIM(soh.cust_key)
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON TRIM(cs.cust_key) = TRIM(soh.cust_key)
                    AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                LEFT JOIN erp_mirror_so_detail sod
                    ON sod.system_id = soh.system_id AND CAST(sod.so_id AS TEXT) = CAST(soh.so_id AS TEXT)
                {where_clause}
                GROUP BY soh.system_id, soh.so_id
                ORDER BY MAX(soh.synced_at) DESC NULLS LAST, soh.so_id DESC
                LIMIT :limit
                """,
                params,
            )
            return [
                {
                    **dict(row),
                    "address": ", ".join(part for part in [row.get("address_1"), row.get("city")] if part),
                }
                for row in rows
            ]

        self._require_central_db_for_cloud_mode()
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            params = []
            clauses = ["UPPER(COALESCE(soh.so_status, '')) = 'O'"]
            if q:
                like = f"%{q}%"
                clauses.append(
                    "(CAST(soh.so_id AS VARCHAR(64)) LIKE ?"
                    " OR COALESCE(c.cust_name, '') LIKE ?"
                    " OR COALESCE(c.cust_code, '') LIKE ?)"
                )
                params.extend([like, like, like])
            if branch:
                system_id = self._normalize_branch_system_id(branch)
                if system_id:
                    clauses.append("soh.system_id = ?")
                    params.append(system_id)
            where_clause = "WHERE " + " AND ".join(clauses)

            cursor.execute(
                f"""
                SELECT TOP {int(limit)}
                    CAST(soh.so_id AS VARCHAR(64)) AS so_number,
                    MAX(c.cust_name) AS customer_name,
                    MAX(c.cust_code) AS customer_code,
                    MAX(cs.address_1) AS address_1,
                    MAX(cs.city) AS city,
                    MAX(soh.expect_date) AS expect_date,
                    MAX(soh.reference) AS reference,
                    MAX(soh.so_status) AS so_status,
                    '' AS handling_code,
                    MAX(soh.sale_type) AS sale_type,
                    MAX(COALESCE(soh.ship_via, '')) AS ship_via,
                    COUNT(DISTINCT sod.sequence) AS line_count
                FROM so_header soh
                LEFT JOIN cust c
                    ON soh.system_id = c.system_id AND c.cust_key = soh.cust_key
                LEFT JOIN cust_shipto cs
                    ON soh.system_id = cs.system_id AND cs.cust_key = soh.cust_key
                    AND cs.seq_num = soh.shipto_seq_num
                LEFT JOIN so_detail sod
                    ON sod.system_id = soh.system_id AND sod.so_id = soh.so_id
                {where_clause}
                GROUP BY soh.system_id, soh.so_id
                ORDER BY MAX(soh.expect_date) DESC, soh.so_id DESC
                """,
                params,
            )
            rows = cursor.fetchall()
            return [
                {
                    "so_number": str(row.so_number),
                    "customer_name": row.customer_name,
                    "customer_code": row.customer_code,
                    "expect_date": row.expect_date,
                    "reference": row.reference,
                    "so_status": row.so_status,
                    "address": ", ".join(part for part in [row.address_1, row.city] if part),
                    "handling_code": "",
                    "sale_type": row.sale_type,
                    "ship_via": row.ship_via,
                    "line_count": row.line_count,
                }
                for row in rows
            ]
        finally:
            cursor.close()
            conn.close()

    def get_sales_invoice_lookup(self, q="", date_from="", date_to="", status="", limit=50, branch=""):
        if self.central_db_mode:
            params = {"limit": limit}
            if status and status.upper() in ('I', 'C'):
                clauses = [f"UPPER(COALESCE(soh.so_status, '')) = '{status.upper()}'"]
            else:
                clauses = ["UPPER(COALESCE(soh.so_status, '')) IN ('I', 'C')"]
            clauses.append("soh.is_deleted = false")
            if q:
                params["q"] = f"%{q}%"
                clauses.append(
                    "(soh.so_id::text ILIKE :q"
                    " OR COALESCE(c.cust_name, '') ILIKE :q"
                    " OR COALESCE(c.cust_code, '') ILIKE :q)"
                )
            if date_from:
                params["date_from"] = date_from
                clauses.append("CAST(COALESCE(sh.invoice_date, soh.expect_date) AS DATE) >= :date_from")
            if date_to:
                params["date_to"] = date_to
                clauses.append("CAST(COALESCE(sh.invoice_date, soh.expect_date) AS DATE) <= :date_to")
            if branch:
                system_id = self._normalize_branch_system_id(branch)
                if system_id:
                    params["branch_id"] = system_id
                    clauses.append("soh.system_id = :branch_id")

            rows = self._mirror_query(
                f"""
                SELECT
                    soh.so_id::text AS so_number,
                    MAX(c.cust_name) AS customer_name,
                    MAX(c.cust_code) AS customer_code,
                    MAX(COALESCE(sh.invoice_date, soh.expect_date)) AS expect_date,
                    MAX(soh.reference) AS reference,
                    MAX(soh.so_status) AS so_status
                FROM erp_mirror_so_header soh
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(c.cust_key) = TRIM(soh.cust_key)
                LEFT JOIN erp_mirror_shipments_header sh
                    ON sh.system_id = soh.system_id AND CAST(sh.so_id AS TEXT) = CAST(soh.so_id AS TEXT)
                WHERE {' AND '.join(clauses)}
                GROUP BY soh.system_id, soh.so_id
                ORDER BY MAX(COALESCE(sh.invoice_date, soh.expect_date)) DESC NULLS LAST, soh.so_id DESC
                LIMIT :limit
                """,
                params,
            )
            return [dict(row) for row in rows]

        self._require_central_db_for_cloud_mode()
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            if status and status.upper() in ('I', 'C'):
                clauses = [f"UPPER(COALESCE(soh.so_status, '')) = '{status.upper()}'"]
            else:
                clauses = ["UPPER(COALESCE(soh.so_status, '')) IN ('I', 'C')"]
            params = []
            if q:
                like = f"%{q}%"
                clauses.append(
                    "(CAST(soh.so_id AS VARCHAR(64)) LIKE ?"
                    " OR COALESCE(c.cust_name, '') LIKE ?"
                    " OR COALESCE(c.cust_code, '') LIKE ?)"
                )
                params.extend([like, like, like])
            if date_from:
                clauses.append("CAST(COALESCE(sh.invoice_date, soh.expect_date) AS DATE) >= ?")
                params.append(date_from)
            if date_to:
                clauses.append("CAST(COALESCE(sh.invoice_date, soh.expect_date) AS DATE) <= ?")
                params.append(date_to)
            if branch:
                system_id = self._normalize_branch_system_id(branch)
                if system_id:
                    clauses.append("soh.system_id = ?")
                    params.append(system_id)

            cursor.execute(
                f"""
                SELECT TOP {int(limit)}
                    CAST(soh.so_id AS VARCHAR(64)) AS so_number,
                    MAX(c.cust_name) AS customer_name,
                    MAX(c.cust_code) AS customer_code,
                    MAX(COALESCE(sh.invoice_date, soh.expect_date)) AS expect_date,
                    MAX(soh.reference) AS reference,
                    MAX(soh.so_status) AS so_status
                FROM so_header soh
                LEFT JOIN cust c
                    ON soh.system_id = c.system_id AND c.cust_key = soh.cust_key
                LEFT JOIN shipments_header sh
                    ON sh.system_id = soh.system_id AND sh.so_id = soh.so_id
                WHERE {" AND ".join(clauses)}
                GROUP BY soh.system_id, soh.so_id
                ORDER BY MAX(COALESCE(sh.invoice_date, soh.expect_date)) DESC, soh.so_id DESC
                """,
                params,
            )
            rows = cursor.fetchall()
            return [
                {
                    "so_number": str(row.so_number),
                    "customer_name": row.customer_name,
                    "customer_code": row.customer_code,
                    "expect_date": row.expect_date,
                    "reference": row.reference,
                    "so_status": row.so_status,
                }
                for row in rows
            ]
        finally:
            cursor.close()
            conn.close()

    def get_sales_customer_orders(self, customer_number, q="", limit=None, date_from="", date_to="", status="", branch="", page=1):
        # Cache per-customer full order lists for up to 60 s (skip cache when filtering/paginating)
        cache_key = f'cust_orders_{customer_number}_{limit}' if not (q or date_from or date_to or status or branch or page > 1) else None
        if cache_key:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached
        result = self._get_sales_customer_orders_inner(
            customer_number=customer_number, q=q, limit=limit,
            date_from=date_from, date_to=date_to, status=status, branch=branch, page=page,
        )
        if cache_key:
            self._cache_set(cache_key, result)
        return result

    def _get_sales_customer_orders_inner(self, customer_number, q="", limit=None, date_from="", date_to="", status="", branch="", page=1):
        if self.central_db_mode:
            sod_columns = set(self._mirror_columns("erp_mirror_so_detail"))
            if "line_no" in sod_columns:
                line_count_expr = "COUNT(DISTINCT sod.line_no) AS line_count"
            elif "sequence" in sod_columns:
                line_count_expr = "COUNT(DISTINCT sod.sequence) AS line_count"
            else:
                line_count_expr = "COUNT(sod.id) AS line_count"
            params = {}
            clauses = ["soh.is_deleted = false"]
            if customer_number:
                params["customer_number"] = f"%{customer_number}%"
                clauses.append(
                    "(COALESCE(c.cust_code, '') ILIKE :customer_number"
                    " OR COALESCE(c.cust_name, '') ILIKE :customer_number)"
                )
            if q:
                params["q"] = f"%{q}%"
                clauses.append(
                    "(soh.so_id::text ILIKE :q"
                    " OR COALESCE(soh.reference, '') ILIKE :q"
                    " OR COALESCE(c.cust_name, '') ILIKE :q"
                    " OR COALESCE(c.cust_code, '') ILIKE :q)"
                )
            if date_from:
                params["date_from"] = date_from
                clauses.append("CAST(soh.expect_date AS DATE) >= :date_from")
            if date_to:
                params["date_to"] = date_to
                clauses.append("CAST(soh.expect_date AS DATE) <= :date_to")
            if status:
                valid_statuses = [s.strip().upper() for s in status.split(',') if s.strip()]
                if valid_statuses:
                    placeholders = ', '.join(f"'{s}'" for s in valid_statuses if s.isalpha() and len(s) == 1)
                    if placeholders:
                        clauses.append(f"UPPER(COALESCE(soh.so_status, '')) IN ({placeholders})")
            if branch:
                system_id = self._normalize_branch_system_id(branch)
                if system_id:
                    params["branch_id"] = system_id
                    clauses.append("soh.system_id = :branch_id")
            page = max(1, page)
            offset = (page - 1) * limit if limit else 0
            if limit:
                params["limit"] = limit
                params["offset"] = offset
                limit_clause = "LIMIT :limit OFFSET :offset"
            else:
                limit_clause = ""
            where_clause = "WHERE " + " AND ".join(clauses)

            rows = self._mirror_query(
                f"""
                SELECT
                    soh.so_id::text AS so_number,
                    MAX(c.cust_name) AS customer_name,
                    MAX(c.cust_code) AS customer_code,
                    MAX(cs.address_1) AS address_1,
                    MAX(cs.city) AS city,
                    MAX(soh.expect_date) AS expect_date,
                    MAX(soh.reference) AS reference,
                    MAX(soh.so_status) AS so_status,
                    MAX(soh.synced_at) AS synced_at,
                    (SELECT MAX(ib.handling_code)
                     FROM erp_mirror_so_detail sod
                     JOIN erp_mirror_item_branch ib
                         ON ib.system_id = sod.system_id AND ib.item_ptr = sod.item_ptr
                     WHERE sod.system_id = soh.system_id AND CAST(sod.so_id AS TEXT) = CAST(soh.so_id AS TEXT)
                    ) AS handling_code,
                    MAX(soh.sale_type) AS sale_type,
                    MAX(COALESCE(soh.ship_via, '')) AS ship_via,
                    {line_count_expr}
                FROM erp_mirror_so_header soh
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(c.cust_key) = TRIM(soh.cust_key)
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON TRIM(cs.cust_key) = TRIM(soh.cust_key)
                    AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                LEFT JOIN erp_mirror_so_detail sod
                    ON sod.system_id = soh.system_id AND CAST(sod.so_id AS TEXT) = CAST(soh.so_id AS TEXT)
                {where_clause}
                GROUP BY soh.system_id, soh.so_id
                ORDER BY MAX(soh.expect_date) DESC NULLS LAST, soh.so_id DESC
                {limit_clause}
                """,
                params,
            )
            return [
                {
                    **dict(row),
                    "address": ", ".join(part for part in [row.get("address_1"), row.get("city")] if part),
                }
                for row in rows
            ]

        self._require_central_db_for_cloud_mode()
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            clauses = []
            params = []
            if customer_number:
                customer_like = f"%{customer_number}%"
                clauses.append(
                    "(COALESCE(c.cust_code, '') LIKE ? OR COALESCE(c.cust_name, '') LIKE ?)"
                )
                params.extend([customer_like, customer_like])
            if q:
                search_like = f"%{q}%"
                clauses.append(
                    "(CAST(soh.so_id AS VARCHAR(64)) LIKE ?"
                    " OR COALESCE(soh.reference, '') LIKE ?"
                    " OR COALESCE(c.cust_name, '') LIKE ?"
                    " OR COALESCE(c.cust_code, '') LIKE ?)"
                )
                params.extend([search_like, search_like, search_like, search_like])
            if date_from:
                clauses.append("CAST(soh.expect_date AS DATE) >= ?")
                params.append(date_from)
            if date_to:
                clauses.append("CAST(soh.expect_date AS DATE) <= ?")
                params.append(date_to)
            if status:
                valid_statuses = [s.strip().upper() for s in status.split(',') if s.strip() and s.strip().isalpha() and len(s.strip()) == 1]
                if valid_statuses:
                    placeholders = ', '.join(f"'{s}'" for s in valid_statuses)
                    clauses.append(f"UPPER(COALESCE(soh.so_status, '')) IN ({placeholders})")
            if branch:
                system_id = self._normalize_branch_system_id(branch)
                if system_id:
                    clauses.append("soh.system_id = ?")
                    params.append(system_id)

            where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            page = max(1, page)
            offset = (page - 1) * limit if limit else 0
            pagination_clause = f"OFFSET ? ROWS FETCH NEXT ? ROWS ONLY" if limit else ""
            if limit:
                params.extend([offset, int(limit)])
            cursor.execute(
                f"""
                SELECT
                    CAST(soh.so_id AS VARCHAR(64)) AS so_number,
                    MAX(c.cust_name) AS customer_name,
                    MAX(c.cust_code) AS customer_code,
                    MAX(cs.address_1) AS address_1,
                    MAX(cs.city) AS city,
                    MAX(soh.expect_date) AS expect_date,
                    MAX(soh.reference) AS reference,
                    MAX(soh.so_status) AS so_status,
                    '' AS handling_code,
                    MAX(soh.sale_type) AS sale_type,
                    MAX(COALESCE(soh.ship_via, '')) AS ship_via,
                    COUNT(DISTINCT sod.sequence) AS line_count
                FROM so_header soh
                LEFT JOIN cust c
                    ON soh.system_id = c.system_id AND c.cust_key = soh.cust_key
                LEFT JOIN cust_shipto cs
                    ON soh.system_id = cs.system_id AND cs.cust_key = soh.cust_key
                    AND cs.seq_num = soh.shipto_seq_num
                LEFT JOIN so_detail sod
                    ON sod.system_id = soh.system_id AND sod.so_id = soh.so_id
                {where_clause}
                GROUP BY soh.system_id, soh.so_id
                ORDER BY MAX(soh.expect_date) DESC, soh.so_id DESC
                {pagination_clause}
                """,
                params,
            )
            rows = cursor.fetchall()
            return [
                {
                    "so_number": str(row.so_number),
                    "customer_name": row.customer_name,
                    "customer_code": row.customer_code,
                    "expect_date": row.expect_date,
                    "reference": row.reference,
                    "so_status": row.so_status,
                    "address": ", ".join(part for part in [row.address_1, row.city] if part),
                    "handling_code": "",
                    "sale_type": row.sale_type,
                    "ship_via": row.ship_via,
                    "line_count": row.line_count,
                }
                for row in rows
            ]
        finally:
            cursor.close()
            conn.close()

    def get_sales_products(self, q="", limit=50):
        if self.central_db_mode:
            qty_expr = self._mirror_item_branch_qty_expr("ib")
            params = {"limit": limit}
            search_filter = ""
            if q:
                params["q"] = f"%{q}%"
                search_filter = """
                  AND (COALESCE(i.item, '') ILIKE :q
                       OR COALESCE(i.description, '') ILIKE :q)
                """
            rows = self._mirror_query(
                f"""
                SELECT
                    i.item AS item_number,
                    i.description,
                    MAX({qty_expr}) AS quantity_on_hand
                FROM erp_mirror_item i
                LEFT JOIN erp_mirror_item_branch ib
                    ON CAST(ib.item_ptr AS TEXT) = CAST(i.item_ptr AS TEXT)
                WHERE i.is_deleted = false
                {search_filter}
                GROUP BY i.item, i.description
                ORDER BY i.item
                LIMIT :limit
                """,
                params,
            )
            return [dict(row) for row in rows]

        self._require_central_db_for_cloud_mode()
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            params = []
            where_clause = ""
            if q:
                like = f"%{q}%"
                where_clause = "WHERE (COALESCE(i.item, '') LIKE ? OR COALESCE(i.description, '') LIKE ?)"
                params.extend([like, like])
            cursor.execute(
                f"""
                SELECT TOP {int(limit)}
                    i.item AS item_number,
                    i.description,
                    MAX(COALESCE(ib.qty_available, ib.qty_on_hand, 0)) AS quantity_on_hand
                FROM item i
                LEFT JOIN item_branch ib
                    ON ib.item_ptr = i.item_ptr
                {where_clause}
                GROUP BY i.item, i.description
                ORDER BY i.item
                """,
                params,
            )
            rows = cursor.fetchall()
            return [
                {
                    "item_number": row.item_number,
                    "description": row.description,
                    "quantity_on_hand": row.quantity_on_hand,
                }
                for row in rows
            ]
        finally:
            cursor.close()
            conn.close()

    def get_sales_reports(self, period_days=30, branch=""):
        cache_key = f'sales_reports_{period_days}_{branch}' if not branch else None
        if cache_key:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached
        result = self._get_sales_reports_inner(period_days=period_days, branch=branch)
        if cache_key:
            self._cache_set(cache_key, result)
        return result

    def _get_sales_reports_inner(self, period_days=30, branch=""):
        if self.central_db_mode:
            since = datetime.utcnow() - timedelta(days=period_days)
            params_base: dict = {"since": since}
            branch_clause = ""
            if branch:
                system_id = self._normalize_branch_system_id(branch)
                if system_id:
                    params_base["branch_id"] = system_id
                    branch_clause = " AND system_id = :branch_id"

            daily_orders = self._mirror_query(
                f"""
                SELECT
                    CAST(expect_date AS DATE) AS expect_date,
                    COUNT(DISTINCT so_id) AS count
                FROM erp_mirror_so_header
                WHERE is_deleted = false
                  AND expect_date IS NOT NULL
                  AND expect_date >= :since
                  {branch_clause}
                GROUP BY CAST(expect_date AS DATE)
                ORDER BY CAST(expect_date AS DATE)
                """,
                params_base,
            )
            branch_join_clause = ""
            if branch and "branch_id" in params_base:
                branch_join_clause = " AND soh.system_id = :branch_id"
            top_customers = self._mirror_query(
                f"""
                SELECT
                    MAX(c.cust_name) AS customer_name,
                    MAX(c.cust_code) AS customer_code,
                    COUNT(DISTINCT soh.so_id) AS order_count
                FROM erp_mirror_so_header soh
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(c.cust_key) = TRIM(soh.cust_key)
                WHERE soh.is_deleted = false
                  AND soh.expect_date >= :since
                  {branch_join_clause}
                GROUP BY c.cust_key
                ORDER BY order_count DESC
                LIMIT 15
                """,
                params_base,
            )
            status_breakdown = self._mirror_query(
                f"""
                SELECT
                    so_status,
                    COUNT(DISTINCT so_id) AS count
                FROM erp_mirror_so_header
                WHERE is_deleted = false
                  AND expect_date >= :since
                  {branch_clause}
                GROUP BY so_status
                ORDER BY count DESC
                """,
                params_base,
            )
            return {
                "daily_orders": [dict(row) for row in daily_orders],
                "top_customers": [dict(row) for row in top_customers],
                "status_breakdown": [dict(row) for row in status_breakdown],
            }

        self._require_central_db_for_cloud_mode()
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            since = datetime.utcnow() - timedelta(days=period_days)

            cursor.execute(
                """
                SELECT
                    CAST(expect_date AS DATE) AS expect_date,
                    COUNT(DISTINCT so_id) AS count
                FROM so_header
                WHERE COALESCE(expect_date, invoice_date, created_date) >= ?
                  AND expect_date IS NOT NULL
                GROUP BY CAST(expect_date AS DATE)
                ORDER BY CAST(expect_date AS DATE)
                """,
                (since,),
            )
            daily_orders = [
                {"expect_date": row.expect_date, "count": row.count}
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT TOP 15
                    MAX(c.cust_name) AS customer_name,
                    MAX(c.cust_code) AS customer_code,
                    COUNT(DISTINCT soh.so_id) AS order_count
                FROM so_header soh
                LEFT JOIN cust c
                    ON soh.system_id = c.system_id AND c.cust_key = soh.cust_key
                WHERE COALESCE(soh.expect_date, soh.invoice_date, soh.created_date) >= ?
                GROUP BY soh.cust_key
                ORDER BY order_count DESC
                """,
                (since,),
            )
            top_customers = [
                {
                    "customer_name": row.customer_name,
                    "customer_code": row.customer_code,
                    "order_count": row.order_count,
                }
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT
                    so_status,
                    COUNT(DISTINCT so_id) AS count
                FROM so_header
                WHERE COALESCE(expect_date, invoice_date, created_date) >= ?
                GROUP BY so_status
                ORDER BY count DESC
                """,
                (since,),
            )
            status_breakdown = [
                {"so_status": row.so_status, "count": row.count}
                for row in cursor.fetchall()
            ]
            return {
                "daily_orders": daily_orders,
                "top_customers": top_customers,
                "status_breakdown": status_breakdown,
            }
        finally:
            cursor.close()
            conn.close()

    def get_sales_customers_search(self, q="", limit=10):
        """Fast customer type-ahead: queries the customer table directly instead of through orders."""
        if len(q) < 2:
            return []
        if self.central_db_mode:
            rows = self._mirror_query(
                """
                SELECT cust_code, cust_name, branch_code
                FROM erp_mirror_cust
                WHERE is_deleted = false
                  AND (
                      cust_code ILIKE :q
                      OR cust_name ILIKE :q
                  )
                ORDER BY cust_name
                LIMIT :limit
                """,
                {"q": f"%{q}%", "limit": limit},
            )
            return [dict(row) for row in rows]

        self._require_central_db_for_cloud_mode()
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            like = f"%{q}%"
            cursor.execute(
                f"""
                SELECT TOP {int(limit)} cust_code, cust_name, branch_code
                FROM cust
                WHERE cust_code LIKE ? OR cust_name LIKE ?
                ORDER BY cust_name
                """,
                (like, like),
            )
            return [
                {"cust_code": row.cust_code, "cust_name": row.cust_name, "branch_code": row.branch_code}
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()
            conn.close()

    def get_open_work_orders(self):
        """
        Fetches all Open Work Orders (wo_status != 'C') from ERP.
        """
        if self.central_db_mode:
            rows = self._mirror_query(
                """
                SELECT
                    wh.wo_id,
                    wh.source_id,
                    COALESCE(i.item, sod_item.item) AS item_number,
                    COALESCE(i.description, sod_item.description) AS description,
                    wh.wo_status,
                    wh.qty,
                    COALESCE(wh.department, wh.wo_rule) AS department,
                    c.cust_name AS customer_name,
                    soh.reference
                FROM erp_mirror_wo_header wh
                LEFT JOIN erp_mirror_so_detail sod
                    ON CAST(sod.so_id AS TEXT) = CAST(wh.source_id AS TEXT)
                   AND sod.sequence = wh.source_seq
                LEFT JOIN erp_mirror_item i
                    ON CAST(i.item_ptr AS TEXT) = CAST(wh.item_ptr AS TEXT)
                LEFT JOIN erp_mirror_item sod_item
                    ON CAST(sod_item.item_ptr AS TEXT) = CAST(sod.item_ptr AS TEXT)
                LEFT JOIN erp_mirror_so_header soh
                    ON CAST(soh.so_id AS TEXT) = CAST(wh.source_id AS TEXT)
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(c.cust_key) = TRIM(soh.cust_key)
                WHERE wh.is_deleted = false
                  AND UPPER(COALESCE(wh.wo_status, '')) NOT IN ('COMPLETED', 'CANCELED', 'C')
                ORDER BY wh.wo_id DESC
                """
            )
            return [{
                'wo_id': row['wo_id'],
                'so_number': row['source_id'],
                'description': row['description'],
                'item_number': row['item_number'],
                'status': row['wo_status'],
                'qty': float(row['qty']) if row['qty'] is not None else 0,
                'department': row['department'],
                'customer_name': row['customer_name'] or 'Unknown',
                'reference': row['reference'] or '',
            } for row in rows]

        self._require_central_db_for_cloud_mode()

        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Enhanced query to include customer and reference
            query = """
                SELECT 
                    wh.wo_id,
                    wh.source_id,
                    i.item as item_number,
                    i.description,
                    wh.wo_status,
                    sod.qty_ordered,
                    wh.wo_rule as department,
                    c.cust_name as customer_name,
                    soh.reference
                FROM wo_header wh
                LEFT JOIN so_detail sod ON wh.source_id = sod.so_id AND wh.source_seq = sod.sequence
                LEFT JOIN item i ON sod.item_ptr = i.item_ptr
                LEFT JOIN so_header soh ON wh.source_id = soh.so_id
                LEFT JOIN cust c ON CAST(soh.cust_key AS VARCHAR) = CAST(c.cust_key AS VARCHAR)
                WHERE wh.wo_status NOT IN ('Completed', 'Canceled')
                ORDER BY wh.wo_id DESC
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            wos = []
            for row in rows:
                wos.append({
                    'wo_id': row.wo_id,
                    'so_number': row.source_id,
                    'description': row.description,
                    'item_number': row.item_number,
                    'status': row.wo_status,
                    'qty': float(row.qty_ordered) if row.qty_ordered is not None else 0,
                    'department': row.department,
                    'customer_name': row.customer_name or 'Unknown',
                    'reference': row.reference or ''
                })
            
            conn.close()
            return wos

        except Exception as e:
            print(f"ERP Connection Error (Open WOs): {e}")
            return []

    def get_sales_delivery_tracker(self, branch_id=None):
        """
        Fetches today's deliveries from ERP, combining SO header and Shipment statuses.
        Returns a list of dictionaries with status, customer, address, and SO info.
        """
        if self.central_db_mode:
            today = datetime.now().strftime('%Y-%m-%d')
            params = {"today": today}
            branch_filter = ""
            system_id = self._normalize_branch_system_id(branch_id)
            if system_id:
                branch_filter = " AND soh.system_id = :branch_id"
                params["branch_id"] = system_id

            rows = self._mirror_query(
                f"""
                SELECT
                    soh.so_id,
                    MAX(c.cust_name) AS cust_name,
                    MAX(cs.address_1) AS address_1,
                    MAX(cs.city) AS city,
                    MAX(soh.reference) AS reference,
                    MAX(soh.so_status) AS so_status,
                    MAX(sh.status_flag) AS shipment_status,
                    MAX(sh.invoice_date) AS invoice_date,
                    MAX(soh.system_id) AS system_id,
                    MAX(soh.expect_date) AS expect_date,
                    MAX(soh.sale_type) AS sale_type,
                    MAX(sh.route_id_char) AS route,
                    MAX(COALESCE(sh.ship_via, soh.ship_via)) AS ship_via,
                    MAX(sh.driver) AS driver,
                    MAX(sh.status_flag_delivery) AS status_flag_delivery
                FROM erp_mirror_so_header soh
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(c.cust_key) = TRIM(soh.cust_key)
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON TRIM(cs.cust_key) = TRIM(soh.cust_key) AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                LEFT JOIN erp_mirror_shipments_header sh
                    ON sh.system_id = soh.system_id AND CAST(sh.so_id AS TEXT) = CAST(soh.so_id AS TEXT)
                WHERE soh.is_deleted = false
                  AND soh.so_status != 'C'
                  {branch_filter}
                  AND (
                    (CAST(soh.expect_date AS DATE) = :today)
                    OR (CAST(sh.ship_date AS DATE) = :today)
                    OR (soh.so_status = 'I' AND CAST(sh.invoice_date AS DATE) = :today)
                    OR (soh.so_status IN ('K', 'P', 'S') AND (CAST(soh.expect_date AS DATE) = :today OR CAST(soh.expect_date AS DATE) < :today))
                  )
                  AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
                GROUP BY soh.system_id, soh.so_id
                ORDER BY MAX(soh.so_id) DESC
                """,
                params,
            )

            deliveries = []
            for row in rows:
                deliveries.append({
                    'so_number': str(row['so_id']),
                    'customer_name': row['cust_name'] or 'Unknown',
                    'address': f"{row['address_1']}, {row['city']}" if row['address_1'] else 'No Address',
                    'reference': row['reference'],
                    'so_status': row['so_status'],
                    'shipment_status': row['shipment_status'],
                    'invoice_date': row['invoice_date'],
                    'system_id': row['system_id'],
                    'expect_date': str(row['expect_date']) if row['expect_date'] else '',
                    'sale_type': row['sale_type'],
                    'route': row['route'] or '',
                    'ship_via': row['ship_via'] or '',
                    'driver': row['driver'] or '',
                    'status_flag_delivery': row['status_flag_delivery'],
                    'status_label': self._get_status_label(row['so_status'], row['shipment_status'], row['status_flag_delivery']),
                })

            so_numbers = [d['so_number'] for d in deliveries]
            local_states = self._get_local_pick_states(so_numbers)
            for delivery in deliveries:
                if delivery['status_label'] == 'PICKING':
                    delivery['status_label'] = local_states.get(delivery['so_number'], 'PICK PRINTED').upper()
            return deliveries
        self._require_central_db_for_cloud_mode()

        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Use today's date for Agility query
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Refined Logic:
            # 1. system_id = '1' for consistency
            # 2. Exclude 'C' (Cancelled)
            # 3. Only show:
            #    - Scheduled for Today (expect_date or ship_date)
            #    - OR Invoiced Today (invoice_date)
            #    - OR Open (K, P, S) ONLY IF scheduled for today (handled by above)
            #    Actually, user wants "daily deliveries", so we filter by date.
            
            query_params = []
            branch_filter = ""
            system_id = self._normalize_branch_system_id(branch_id)
            if system_id:
                branch_filter = " AND soh.system_id = ?"
                query_params.append(system_id)

            query = f"""
                SELECT 
                    soh.so_id,
                    MAX(c.cust_name) as cust_name,
                    MAX(cs.address_1) as address_1,
                    MAX(cs.city) as city,
                    MAX(soh.reference) as reference,
                    MAX(soh.so_status) as so_status,
                MAX(sh.status_flag) as shipment_status,
                MAX(sh.invoice_date) as invoice_date,
                MAX(soh.system_id) as system_id,
                MAX(soh.expect_date) as expect_date,
                MAX(soh.sale_type) as sale_type,
                MAX(sh.route_id_char) as route,
                MAX(sh.ship_via) as ship_via,
                MAX(sh.driver) as driver,
                MAX(sh.status_flag_delivery) as status_flag_delivery
                FROM so_header soh
                LEFT JOIN cust c ON soh.system_id = c.system_id AND TRY_CAST(soh.cust_key AS INT) = TRY_CAST(c.cust_key AS INT)
                LEFT JOIN cust_shipto cs ON soh.system_id = cs.system_id AND TRY_CAST(soh.cust_key AS INT) = TRY_CAST(cs.cust_key AS INT) AND TRY_CAST(soh.shipto_seq_num AS INT) = TRY_CAST(cs.seq_num AS INT)
                LEFT JOIN shipments_header sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
                WHERE soh.so_status != 'C'
                  {branch_filter}
                  AND (
                    (soh.expect_date = ?)
                    OR (sh.ship_date = ?)
                    OR (soh.so_status = 'I' AND sh.invoice_date = ?)
                    OR (soh.so_status IN ('K', 'P', 'S') AND (soh.expect_date = ? OR soh.expect_date < ?)) -- Show backlog too but avoid future ones
                  )
                  AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
                GROUP BY soh.system_id, soh.so_id
                ORDER BY MAX(soh.so_id) DESC
            """

            query_params.extend([today, today, today, today, today])
            cursor.execute(query, query_params)
            rows = cursor.fetchall()
            
            deliveries = []
            for row in rows:
                deliveries.append({
                    'so_number': str(row.so_id),
                    'customer_name': row.cust_name or 'Unknown',
                    'address': f"{row.address_1}, {row.city}" if row.address_1 else 'No Address',
                    'reference': row.reference,
                    'so_status': row.so_status,
                    'shipment_status': row.shipment_status,
                    'invoice_date': row.invoice_date,
                    'system_id': row.system_id,
                    'expect_date': str(row.expect_date) if row.expect_date else '',
                    'sale_type': row.sale_type,
                    'route': row.route or '',
                    'ship_via': row.ship_via or '',
                    'driver': row.driver or '',
                    'status_flag_delivery': row.status_flag_delivery,
                    'status_label': self._get_status_label(row.so_status, row.shipment_status, row.status_flag_delivery)
                })
            conn.close()
            
            # Merge local pick states to override 'PICKING' label
            so_numbers = [d['so_number'] for d in deliveries]
            local_states = self._get_local_pick_states(so_numbers)
            
            for d in deliveries:
                if d['status_label'] == 'PICKING':
                    # Instead of generic 'PICKING', use the specific granular state
                    d['status_label'] = local_states.get(d['so_number'], 'PICK PRINTED').upper()
                    
            return deliveries

        except Exception as e:
            print(f"ERP Connection Error (Sales Tracker): {e}")
            return []

    def get_historical_delivery_stats(self, days=7, branch_id=None):
        """
        Fetches historical delivery counts by date for the last X days from local ERP.
        Used by the sync service to populate KPI tables.
        """
        if self.central_db_mode:
            params = {"days": int(days)}
            branch_filter = ""
            system_id = self._normalize_branch_system_id(branch_id)
            if system_id:
                branch_filter = " AND soh.system_id = :branch_id"
                params["branch_id"] = system_id

            rows = self._mirror_query(
                f"""
                SELECT
                    CAST(sh.ship_date AS DATE) AS ship_date,
                    COUNT(DISTINCT soh.so_id) AS count
                FROM erp_mirror_so_header soh
                JOIN erp_mirror_shipments_header sh
                    ON sh.system_id = soh.system_id
                   AND CAST(sh.so_id AS TEXT) = CAST(soh.so_id AS TEXT)
                WHERE soh.is_deleted = false
                  AND CAST(sh.ship_date AS DATE) >= CURRENT_DATE - (:days * INTERVAL '1 day')
                  AND CAST(sh.ship_date AS DATE) < CURRENT_DATE
                  AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
                  {branch_filter}
                GROUP BY CAST(sh.ship_date AS DATE)
                ORDER BY CAST(sh.ship_date AS DATE) DESC
                """,
                params,
            )
            return [{
                'date': row['ship_date'].strftime('%Y-%m-%d') if hasattr(row['ship_date'], 'strftime') else str(row['ship_date']).split(' ')[0],
                'count': row['count'],
                'branch': branch_id or 'all',
            } for row in rows]

        if self.cloud_mode:
            return [] # Local only

        try:
            branch_filter = ""
            query_params = []
            system_id = self._normalize_branch_system_id(branch_id)
            if system_id:
                branch_filter = " AND soh.system_id = ?"
                query_params.append(system_id)

            query = f"""
                SELECT 
                    sh.ship_date,
                    COUNT(DISTINCT soh.so_id) as count
                FROM so_header soh
                JOIN shipments_header sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
                WHERE sh.ship_date >= CAST(DATEADD(day, -{days}, GETDATE()) AS DATE)
                  AND sh.ship_date < CAST(GETDATE() AS DATE)
                  AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
                  {branch_filter}
                GROUP BY sh.ship_date
                ORDER BY sh.ship_date DESC
            """
            
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, query_params)
            rows = cursor.fetchall()
            
            stats = []
            for row in rows:
                date_val = row.ship_date
                if hasattr(date_val, 'strftime'):
                    date_str = date_val.strftime('%Y-%m-%d')
                else:
                    date_str = str(date_val).split(' ')[0]
                    
                stats.append({
                    'date': date_str,
                    'count': row.count,
                    'branch': branch_id or 'all'
                })
            
            conn.close()
            return stats

        except Exception as e:
            print(f"ERP Connection Error (Historical Stats): {e}")
            return []

    def get_delivery_kpis(self, branch_id=None):
        """
        Fetches aggregated KPI data (7-day average, yesterday's total) from historical mirror stats.
        """
        if self.central_db_mode:
            stats = self.get_historical_delivery_stats(days=14, branch_id=branch_id)
            if not stats:
                return {'avg_7d': 0, 'yesterday': 0}

            stats_by_date = {}
            for row in stats:
                try:
                    stats_by_date[str(row.get('date'))] = int(row.get('count') or 0)
                except Exception:
                    continue

            yesterday = date.today() - timedelta(days=1)
            yesterday_key = yesterday.isoformat()
            yesterday_total = stats_by_date.get(yesterday_key, 0)

            last_7 = []
            for offset in range(1, 8):
                day_key = (date.today() - timedelta(days=offset)).isoformat()
                last_7.append(stats_by_date.get(day_key, 0))

            avg_7d = sum(last_7) / len(last_7) if last_7 else 0
            return {
                'avg_7d': round(avg_7d, 1),
                'yesterday': yesterday_total,
            }

        # Legacy ERPDeliveryKPI table has been retired.
        # Fall through to historical stats calculation for all modes.
        stats = self.get_historical_delivery_stats(days=14, branch_id=branch_id)
        if not stats:
            return {'avg_7d': 0, 'yesterday': 0}

        stats_by_date = {}
        for row in stats:
            try:
                stats_by_date[str(row.get('date'))] = int(row.get('count') or 0)
            except Exception:
                continue

        yesterday = date.today() - timedelta(days=1)
        yesterday_total = stats_by_date.get(yesterday.isoformat(), 0)

        last_7 = []
        for offset in range(1, 8):
            day_key = (date.today() - timedelta(days=offset)).isoformat()
            last_7.append(stats_by_date.get(day_key, 0))

        avg_7d = sum(last_7) / len(last_7) if last_7 else 0
        return {
            'avg_7d': round(avg_7d, 1),
            'yesterday': yesterday_total,
        }
