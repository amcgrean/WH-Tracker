import csv
import os
from datetime import date, datetime
from app.Models.models import ERPMirrorPick, ERPMirrorWorkOrder
from app.runtime_settings import build_sql_connection_strings, env_bool, get_central_db_url, get_sql_server_settings

try:
    import pyodbc
except (ImportError, OSError):
    pyodbc = None

class ERPService:
    def __init__(self):
        self.sql_settings = get_sql_server_settings()
        self.cloud_mode = env_bool('CLOUD_MODE', False)
        
        # Central DB Mode: Active if CENTRAL_DB_URL is set in config/env
        central_url = get_central_db_url() or ''
        self.central_db_mode = bool(central_url)
        
        print(f"ERPService Init: CLOUD_MODE={self.cloud_mode}, CENTRAL_DB_MODE={self.central_db_mode}")
        self._gps_cache = None
        
    def get_connection(self):
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
        """
        # Import inside method to avoid circular imports if models import ERPService
        from app.Models.models import Pick
        from app.extensions import db
        
        query = db.session.query(Pick)
        if so_numbers:
            query = query.filter(Pick.barcode_number.in_(so_numbers))
            
        picks = query.all()
        
        states = {}
        for p in picks:
            so = p.barcode_number
            # If multiple picks exist for an SO, we want the "most active" state.
            # Picking Complete < Pick Printed < Picking
            current_state = states.get(so, 'Pick Printed')
            
            new_state = 'Pick Printed'
            if p.start_time and not p.completed_time:
                new_state = 'Picking'
            elif p.completed_time:
                new_state = 'Picking Complete'
                
            # Upgrade state if necessary
            if new_state == 'Picking':
                states[so] = 'Picking'
            elif new_state == 'Picking Complete' and current_state != 'Picking':
                 states[so] = 'Picking Complete'
            elif current_state not in states:
                 states[so] = new_state
                 
        return states
        
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
        if self.cloud_mode:
            wos = ERPMirrorWorkOrder.query.filter_by(so_number=barcode).all()
            return [{
                'wo_number': wo.wo_id,
                'item_number': wo.item_number,
                'description': wo.description,
                'status': wo.status,
                'handling_code': wo.department
            } for wo in wos]

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
            
            if not results:
                 # Keep mock data alive for standard testing if DB returns nothing
                 return [
                    {'wo_number': f'WO-{barcode}-001', 'item_number': '874125', 'description': 'Interior Door - Oak (Mock)', 'handling_code': 'HC-A'},
                    {'wo_number': f'WO-{barcode}-002', 'item_number': '874128', 'description': 'Exterior Frame - Pine (Mock)', 'handling_code': 'HC-B'},
                ]
            
            return results

        except Exception as e:
            print(f"ERP Connection Error: {e}")
            # Fallback for dev/demo if connection fails
            return [
                {'wo_number': f'WO-{barcode}-ERR', 'item_number': 'ERROR', 'description': f'Connection Failed: {e}', 'handling_code': 'ERR'}
            ]

    def get_open_picks(self):
        """
        Fetches all open picks (status 'k') from the ERP, joined with details and handling codes.
        Returns a list of dictionaries.
        """
        if self.central_db_mode:
            # Example pattern for querying the new Central DB models
            # from app.Models.central_db import CentralSalesOrder, CentralSalesOrderLine
            # 
            # query = db.session.query(CentralSalesOrderLine, CentralSalesOrder).join(...)
            # return [{ mapped_fields }]
            print("Central DB Mode active - redirecting to central Postgres DB (implementation pending finalization of local queries)")
            pass # Fallthrough or return central db results once queries are built out

        if self.cloud_mode:
            picks = ERPMirrorPick.query.all()
            return [{
                'so_number': p.so_number,
                'customer_name': p.customer_name,
                'address': p.address,
                'reference': p.reference,
                'handling_code': p.handling_code,
                'sequence': p.sequence,
                'item_number': p.item_number,
                'description': p.description,
                'qty': p.qty,
            'line_count': 1,
            'so_status': p.so_status,
            'shipment_status': p.shipment_status,
            'system_id': p.system_id,
            'expect_date': p.expect_date,
            'local_pick_state': p.local_pick_state,
            'ship_via': p.ship_via,
            'driver': p.driver,
            'route': p.route,
            'printed_at': p.printed_at,
            'staged_at': p.staged_at,
            'delivered_at': p.delivered_at,
            'status_flag_delivery': p.status_flag_delivery
        } for p in picks]

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
                LEFT JOIN cust c ON TRY_CAST(soh.cust_key AS INT) = TRY_CAST(c.cust_key AS INT)
                LEFT JOIN cust_shipto cs ON TRY_CAST(soh.cust_key AS INT) = TRY_CAST(cs.cust_key AS INT) AND TRY_CAST(soh.shipto_seq_num AS INT) = TRY_CAST(cs.seq_num AS INT)
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

    def get_open_so_summary(self):
        """
        Fetches a summary of Open Sales Orders (Status 'K'), grouped by Handling Code.
        Returns: List of dicts {so_number, customer_name, address, reference, handling_code, line_count}
        """
        if self.cloud_mode:
            from sqlalchemy import func
            from app.extensions import db
            # Aggregate lines by SO and Handling Code
            summary_query = db.session.query(
                ERPMirrorPick.so_number,
                ERPMirrorPick.customer_name,
                ERPMirrorPick.address,
                ERPMirrorPick.reference,
                ERPMirrorPick.handling_code,
                func.max(ERPMirrorPick.local_pick_state).label('local_pick_state'),
                func.count(ERPMirrorPick.id).label('line_count')
            ).group_by(
                ERPMirrorPick.so_number,
                ERPMirrorPick.customer_name,
                ERPMirrorPick.address,
                ERPMirrorPick.reference,
                ERPMirrorPick.handling_code
            ).all()
            
            return [{
                'so_number': s.so_number,
                'customer_name': s.customer_name,
                'address': s.address,
                'reference': s.reference,
                'handling_code': s.handling_code,
                'line_count': s.line_count,
                'local_pick_state': s.local_pick_state  # Now aggregated correctly
            } for s in summary_query]

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
        if self.cloud_mode:
            query = ERPMirrorPick.query
            if so_numbers:
                query = query.filter(ERPMirrorPick.so_number.in_(so_numbers))
            picks = query.all()
            return [{
                'so_number': p.so_number,
                'customer_name': p.customer_name,
                'address': p.address,
                'reference': p.reference,
                'handling_code': p.handling_code,
                'line_count': p.line_count
            } for p in picks]

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
        if self.cloud_mode:
            p = ERPMirrorPick.query.filter_by(so_number=so_number).first()
            if p:
                return {
                    'so_number': p.so_number,
                    'customer_name': p.customer_name,
                    'address': p.address,
                    'reference': p.reference,
                    'system_id': p.system_id,
                    'ship_via': p.ship_via,
                    'driver': p.driver,
                    'route': p.route,
                    'printed_at': p.printed_at,
                    'staged_at': p.staged_at,
                    'delivered_at': p.delivered_at
                }
            return None

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
                    'staged_at': f"{row.loaded_date} {row.loaded_time}" if row.loaded_date else None,
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
        if self.cloud_mode:
            # First try to find individual pick lines
            pick_lines = ERPMirrorPick.query.filter_by(so_number=so_number).order_by(ERPMirrorPick.sequence.asc()).all()
            if pick_lines and any(p.item_number for p in pick_lines):
                return [{
                    'so_number': p.so_number,
                    'sequence': p.sequence,
                    'item_number': p.item_number,
                    'description': p.description,
                    'handling_code': p.handling_code,
                    'qty': p.qty
                } for p in pick_lines]

            # Fallback to Work Orders
            wos = ERPMirrorWorkOrder.query.filter_by(so_number=so_number).order_by(ERPMirrorWorkOrder.id.asc()).all()
            return [{
                'so_number': wo.so_number,
                'sequence': i + 1,
                'item_number': wo.item_number,
                'description': wo.description,
                'handling_code': wo.department,
                'qty': wo.qty
            } for i, wo in enumerate(wos)]

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
                  AND sod.bo = 0
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
        if self.cloud_mode:
            query = ERPMirrorPick.query

            if branches:
                raw_branches = [item.strip().upper() for item in branches.split(",") if item.strip()]
                expanded = []
                for branch in raw_branches:
                    if branch in ("GRIMES", "GRIMES AREA", "GRIMES_AREA"):
                        expanded.extend(["20GR", "25BW"])
                    else:
                        expanded.append(branch)
                expanded = sorted(set(expanded))
                if expanded:
                    query = query.filter(ERPMirrorPick.system_id.in_(expanded))

            if sale_types:
                types = [item.strip() for item in sale_types.split(",") if item.strip()]
                if types:
                    query = query.filter(ERPMirrorPick.sale_type.in_(types))

            if status_filter:
                statuses = [item.strip().upper() for item in status_filter.split(",") if item.strip()]
                if statuses:
                    query = query.filter(ERPMirrorPick.so_status.in_(statuses))

            if route_id:
                query = query.filter(ERPMirrorPick.route == route_id)
            if driver:
                query = query.filter(ERPMirrorPick.driver == driver)

            picks = query.all()
            grouped = {}
            for pick in picks:
                key = str(pick.so_number)
                if key not in grouped:
                    doc_kind = 'credit' if str(pick.so_status or '').upper() == 'CM' else 'delivery'
                    grouped[key] = {
                        'id': int(pick.so_number) if str(pick.so_number).isdigit() else pick.so_number,
                        'doc_kind': doc_kind,
                        'expected_date': str(pick.expect_date or ''),
                        'lat': pick.latitude,
                        'lon': pick.longitude,
                        'address': pick.address or '',
                        'so_status': pick.so_status,
                        'so_type': 'CM' if doc_kind == 'credit' else 'SO',
                        'shipto_name': pick.customer_name or 'Unknown',
                        'shipment_num': None,
                        'route_id': pick.route or '',
                        'driver': pick.driver or '',
                        'branch': pick.system_id or '',
                        'item_count': 0,
                        'total_weight': None,
                        'gps_status': pick.geocode_status or ('exact' if pick.latitude is not None and pick.longitude is not None else 'missing'),
                        'gps_verified': str(pick.geocode_status or '').lower() == 'exact',
                    }
                grouped[key]['item_count'] += 1

            rows = []
            for row in grouped.values():
                include_row = row['doc_kind'] == 'credit'
                expected = row.get('expected_date') or ''
                if expected:
                    try:
                        parsed = datetime.fromisoformat(str(expected)).date()
                        include_row = include_row or (start <= parsed <= end)
                    except Exception:
                        pass
                if include_row:
                    rows.append(row)

            if not include_no_gps:
                rows = [row for row in rows if row.get('lat') is not None and row.get('lon') is not None]

            rows.sort(key=lambda item: (str(item.get('expected_date') or ''), str(item.get('id'))))
            return rows

        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            filters = [
                "("
                " (UPPER(hdr.[type]) = 'CM' AND UPPER(hdr.so_status) NOT IN ('I','C','X','CAN','CANCEL','CANCELED','CN','VOID'))"
                " OR "
                " (UPPER(hdr.[type]) <> 'CM' AND COALESCE(sh.expect_date, hdr.expect_date) BETWEEN ? AND ?)"
                ")",
                "hdr.so_status <> 'I'",
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
                raw_branches = [item.strip().upper() for item in branches.split(",") if item.strip()]
                expanded = []
                for branch in raw_branches:
                    if branch in ("GRIMES", "GRIMES AREA", "GRIMES_AREA"):
                        expanded.extend(["20GR", "25BW"])
                    else:
                        expanded.append(branch)
                expanded = sorted(set(expanded))
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
                    st.shipto_name,
                    cust.cust_code AS CustomerCode,
                    CAST(hdr.shipto_seq_num AS nvarchar(32)) AS ShipToNumber,
                    sh.shipment_num AS shipment_num,
                    COALESCE(sh.route_id_char, hdr.route_id_char) AS route_id,
                    COALESCE(sh.driver, hdr.driver) AS driver,
                    hdr.system_id AS branch
                FROM SO_HEADER hdr
                LEFT JOIN CUST_SHIPTO st ON st.cust_shipto_guid = hdr.cust_shipto_guid
                LEFT JOIN SHIPMENTS_HEADER sh ON sh.so_id = hdr.so_id
                LEFT JOIN CUST cust ON cust.cust_key = hdr.cust_key
                WHERE {" AND ".join(filters)}
            )
            SELECT
                id, doc_kind, expected_date, lat, lon, address,
                so_status, so_type, shipto_name,
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
        if self.cloud_mode:
            picks = ERPMirrorPick.query.filter_by(so_number=str(so_id)).order_by(ERPMirrorPick.sequence.asc()).all()
            lines = [{
                'so_id': so_id,
                'shipment_num': shipment_num,
                'line_no': pick.sequence,
                'item_id': pick.item_number,
                'item_description': pick.description,
                'qty_ordered': pick.qty,
                'qty_shipped': pick.qty,
                'uom': '',
                'weight': None,
            } for pick in picks]
            return lines[:limit]

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
        if self.cloud_mode:
            picks = ERPMirrorPick.query.all()
            # Aggregate by SO number for delivery view
            so_map = {}
            for p in picks:
                so_num = p.so_number
                if so_num not in so_map:
                    so_s = (p.so_status or '').upper()
                    ship_s = (p.shipment_status or '').upper()
                    deliv_s = (p.status_flag_delivery or '').upper()
                    
                    # Compute status label for Cloud Mode
                    label = self._get_status_label(so_s, ship_s, deliv_s)

                    so_map[so_num] = {
                        'so_number': so_num,
                        'customer_name': p.customer_name or 'Unknown',
                        'address': p.address or 'No Address',
                        'reference': p.reference,
                        'handling_codes': [],
                        'line_count': 0,
                        'so_status': so_s,
                        'shipment_status': ship_s,
                        'status_label': label or 'OPEN'
                    }
                if p.handling_code and p.handling_code not in so_map[so_num]['handling_codes']:
                    so_map[so_num]['handling_codes'].append(p.handling_code)
                so_map[so_num]['line_count'] += p.line_count or 0

            results = []
            for so_num, data in so_map.items():
                data['handling_codes'] = sorted(list(data['handling_codes']))
                results.append(data)
            return results

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

    def get_open_work_orders(self):
        """
        Fetches all Open Work Orders (wo_status != 'C') from ERP.
        """
        if self.cloud_mode:
            wos = ERPMirrorWorkOrder.query.all()
            
            # Try to enrich with customer info from Picks if available
            so_numbers = list(set([str(wo.so_number) for wo in wos]))
            so_info = {}
            if so_numbers:
                picks = ERPMirrorPick.query.filter(ERPMirrorPick.so_number.in_(so_numbers)).all()
                for p in picks:
                    if p.so_number not in so_info:
                        so_info[p.so_number] = {
                            'customer_name': p.customer_name,
                            'reference': p.reference
                        }

            return [{
                'wo_id': wo.wo_id,
                'so_number': wo.so_number,
                'description': wo.description,
                'item_number': wo.item_number,
                'status': wo.status,
                'qty': wo.qty,
                'department': wo.department,
                'customer_name': so_info.get(str(wo.so_number), {}).get('customer_name', 'Unknown'),
                'reference': so_info.get(str(wo.so_number), {}).get('reference', '')
            } for wo in wos]

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
        if self.cloud_mode:
            # Fallback to picks mirror for now (could be enhanced with more fields if synced)
            query = ERPMirrorPick.query
            if branch_id:
                query = query.filter(ERPMirrorPick.system_id.ilike(f"%{branch_id}%"))
            picks = query.all()
            
            # Group by SO Number to avoid duplicates in cloud mode
            grouped = {}
            for p in picks:
                if p.so_number not in grouped:
                    # Determine status label in cloud mode based on synced flags
                    so_s = (p.so_status or '').upper()
                    ship_s = (p.shipment_status or '').upper()
                    deliv_s = (p.status_flag_delivery or '').upper()
                    
                    label = self._get_status_label(so_s, ship_s, deliv_s)

                    grouped[p.so_number] = {
                        'so_number': p.so_number,
                        'customer_name': p.customer_name or 'Unknown',
                        'address': p.address or 'No Address',
                        'reference': p.reference,
                        'so_status': so_s,
                    'shipment_status': ship_s,
                    'status_label': label or 'OPEN',
                    'system_id': p.system_id,
                    'expect_date': p.expect_date,
                    'invoice_date': None, # Date details not mirrored yet
                    'local_pick_state': getattr(p, 'local_pick_state', 'Pick Printed'),  # Add default if missing
                    'route': getattr(p, 'route', ''),
                    'ship_via': getattr(p, 'ship_via', ''),
                    'driver': getattr(p, 'driver', ''),
                    'printed_at': getattr(p, 'printed_at', None),
                    'staged_at': getattr(p, 'staged_at', None),
                    'delivered_at': getattr(p, 'delivered_at', None),
                    'status_flag_delivery': getattr(p, 'status_flag_delivery', None)
                }
            # Return as a list, sorted by SO number descending
            return sorted(grouped.values(), key=lambda x: str(x['so_number']), reverse=True)

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
            if branch_id:
                branch_filter = " AND soh.system_id = ?"
                query_params.append(branch_id)

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
                LEFT JOIN cust c ON TRY_CAST(soh.cust_key AS INT) = TRY_CAST(c.cust_key AS INT)
                LEFT JOIN cust_shipto cs ON TRY_CAST(soh.cust_key AS INT) = TRY_CAST(cs.cust_key AS INT) AND TRY_CAST(soh.shipto_seq_num AS INT) = TRY_CAST(cs.seq_num AS INT)
                LEFT JOIN shipments_header sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
                WHERE soh.so_status != 'C'
                  {branch_filter}
                  AND (
                    (soh.expect_date = '{today}')
                    OR (sh.ship_date = '{today}')
                    OR (soh.so_status = 'I' AND sh.invoice_date = '{today}')
                    OR (soh.so_status IN ('K', 'P', 'S') AND (soh.expect_date = '{today}' OR soh.expect_date < '{today}')) -- Show backlog too but avoid future ones
                  )
                  AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
                GROUP BY soh.so_id
                ORDER BY soh.so_id DESC
            """
            
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
                    'status_label': row.status_label,
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
        if self.cloud_mode:
            return [] # Local only

        try:
            branch_map = {
                '20gr': '20GR',
                '25bw': '25BW',
                '10fd': '10FD',
                '40cv': '40CV'
            }
            
            branch_filter = ""
            query_params = []
            if branch_id and branch_id.lower() != 'all':
                normalized_id = branch_id.lower()
                sys_id = branch_map.get(normalized_id, branch_id.upper()) # Fallback to uppercase
                branch_filter = " AND soh.system_id = ?"
                query_params.append(sys_id)

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
        Fetches aggregated KPI data (7-day average, yesterday's total).
        Local Mode: Queries ERP directly.
        Cloud Mode: Queries ERPDeliveryKPI mirror table.
        """
        if self.cloud_mode:
            from app.Models.models import ERPDeliveryKPI
            from sqlalchemy import func
            
            query = ERPDeliveryKPI.query
            if branch_id:
                query = query.filter_by(branch=branch_id)
            else:
                query = query.filter_by(branch='all')
            
            kpis = query.order_by(ERPDeliveryKPI.date.desc()).limit(14).all()
            if not kpis:
                return {'avg_7d': 0, 'yesterday': 0}
            
            yesterday_total = kpis[0].count if kpis else 0
            # Avg of last 7 points
            last_7 = kpis[:7]
            avg_7d = sum(k.count for k in last_7) / len(last_7) if last_7 else 0
            
            return {
                'avg_7d': round(avg_7d, 1),
                'yesterday': yesterday_total
            }
        else:
            # Local: Fetch raw and summarize
            stats = self.get_historical_delivery_stats(days=14, branch_id=branch_id)
            if not stats:
                return {'avg_7d': 0, 'yesterday': 0}
            
            yesterday_total = stats[0]['count'] if stats else 0
            last_7 = stats[:7]
            avg_7d = sum(s['count'] for s in last_7) / len(last_7) if last_7 else 0
            
            return {
                'avg_7d': round(avg_7d, 1),
                'yesterday': yesterday_total
            }
