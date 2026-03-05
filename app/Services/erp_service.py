import os
from datetime import datetime
from app.Models.models import ERPMirrorPick, ERPMirrorWorkOrder

try:
    import pyodbc
except (ImportError, OSError):
    pyodbc = None

class ERPService:
    def __init__(self):
        # Configuration - in production move these to config.py/env vars
        self.server = '10.1.1.17'
        self.database = 'AgilitySQL'
        self.username = 'amcgrean'
        self.password = 'Forgefrog69!'
        self.driver = '{ODBC Driver 17 for SQL Server}'
        raw_mode = os.environ.get('CLOUD_MODE', '')
        self.cloud_mode = str(raw_mode).lower() == 'true'
        print(f"ERPService Init: CLOUD_MODE raw='{raw_mode}', parsed={self.cloud_mode}")
        
    def get_connection(self):
        if pyodbc is None:
            raise RuntimeError("pyodbc is not installed. Set CLOUD_MODE=True for serverless deployments.")
        connection_string = f'DRIVER={self.driver};SERVER={self.server};DATABASE={self.database};UID={self.username};PWD={self.password}'
        return pyodbc.connect(connection_string)
        
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
            'delivered_at': p.delivered_at
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
                sh.ship_date
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
                           MAX(loaded_date) as loaded_date
                    FROM shipments_header 
                    GROUP BY so_id, system_id
                ) sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
                LEFT JOIN (
                    SELECT so_id, system_id,
                           MAX(created_date) as created_date,
                           MAX(created_time) as created_time
                    FROM pick_header
                    WHERE print_status = 'Pick Ticket'
                    GROUP BY so_id, system_id
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
                'delivered_at': f"{row.ship_date}" if row.ship_date else None
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
                    
                    # Compute status label for Cloud Mode
                    label = so_s
                    if so_s == 'K': label = 'PICKING'
                    elif so_s == 'P': label = 'PARTIAL'
                    elif so_s == 'S':
                        if ship_s == 'E': label = 'STAGED - EN ROUTE'
                        elif ship_s == 'L': label = 'STAGED - LOADED'
                        elif ship_s == 'D': label = 'STAGED - DELIVERED'
                        else: label = 'STAGED'
                    elif so_s == 'I': label = 'INVOICED'

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
                    
                    label = so_s
                    if so_s == 'K': label = 'PICKING'
                    elif so_s == 'P': label = 'PARTIAL'
                    elif so_s == 'S':
                        if ship_s == 'E': label = 'STAGED - EN ROUTE'
                        elif ship_s == 'L': label = 'STAGED - LOADED'
                        elif ship_s == 'D': label = 'STAGED - DELIVERED'
                        else: label = 'STAGED'
                    elif so_s == 'I': label = 'INVOICED'

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
                    'delivered_at': getattr(p, 'delivered_at', None)
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
                CASE 
                    WHEN MAX(soh.so_status) = 'K' THEN 'PICKING'
                        WHEN MAX(soh.so_status) = 'P' THEN 'PARTIAL'
                        WHEN MAX(soh.so_status) = 'S' THEN 
                            CASE 
                                WHEN MAX(sh.status_flag) = 'E' THEN 'STAGED - EN ROUTE'
                                WHEN MAX(sh.status_flag) = 'L' THEN 'STAGED - LOADED'
                                WHEN MAX(sh.status_flag) = 'D' THEN 'STAGED - DELIVERED'
                                ELSE 'STAGED'
                            END
                        WHEN MAX(soh.so_status) = 'I' THEN 'INVOICED'
                        ELSE MAX(soh.so_status)
                    END as status_label
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
                    'driver': row.driver or ''
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
