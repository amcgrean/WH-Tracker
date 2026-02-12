import os
from datetime import datetime
from app.Models.models import ERPMirrorPick, ERPMirrorWorkOrder

try:
    import pyodbc
except ImportError:
    pyodbc = None

class ERPService:
    def __init__(self):
        # Configuration - in production move these to config.py/env vars
        self.server = '10.1.1.17'
        self.database = 'AgilitySQL'
        self.username = 'amcgrean'
        self.password = 'Forgefrog69!'
        self.driver = '{ODBC Driver 17 for SQL Server}'
        self.cloud_mode = os.environ.get('CLOUD_MODE') == 'True'
        
    def get_connection(self):
        if pyodbc is None:
            raise RuntimeError("pyodbc is not installed. Set CLOUD_MODE=True for serverless deployments.")
        connection_string = f'DRIVER={self.driver};SERVER={self.server};DATABASE={self.database};UID={self.username};PWD={self.password}'
        return pyodbc.connect(connection_string)

    def get_work_orders_by_barcode(self, barcode):
        """
        Queries the ERP system for work orders associated with a Sales Order barcode.
        """
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
                WHERE soh.so_status = 'k' 
                  AND sod.bo = 0
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
                    'qty': row.qty_ordered
                })
                
            conn.close()
            
            if not picks:
                # Debugging: Return a mock item to indicate 0 rows were found (vs connection error)
                return [{
                    'so_number': '00000',
                    'sequence': 1,
                    'item_number': 'DEBUG',
                    'description': 'Query returned 0 rows. Check Status=K and BO=0 in SSMS.',
                    'handling_code': 'DEBUG',
                    'qty': 0
                }]
                
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
            picks = ERPMirrorPick.query.all()
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
                LEFT JOIN cust c ON soh.cust_key = c.cust_key 
                JOIN cust_shipto cs ON cs.cust_key = soh.cust_key AND cs.seq_num = soh.shipto_seq_num
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
                        'line_count': row.line_count
                    })
            
            conn.close()
            return summary

        except Exception as e:
            print(f"ERP Connection Error (Open Summary): {e}")
            return []

    def get_historical_so_summary(self, so_numbers=None):
        """
        Fetches summary info for specific SOs (or all if None), ignoring status constraints.
        Useful for statistics and historical lookups.
        """
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
                LEFT JOIN cust c ON soh.cust_key = c.cust_key 
                JOIN cust_shipto cs ON cs.cust_key = soh.cust_key AND cs.seq_num = soh.shipto_seq_num
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
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            query = """
                SELECT TOP 1
                    soh.so_id,
                    c.cust_name,
                    cs.address_1,
                    cs.city,
                    soh.reference
                FROM so_header soh
                LEFT JOIN cust c ON soh.cust_key = c.cust_key
                JOIN cust_shipto cs ON cs.cust_key = soh.cust_key AND cs.seq_num = soh.shipto_seq_num
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
                    'reference': row.reference
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

    def get_open_work_orders(self):
        """
        Fetches all Open Work Orders (wo_status != 'C') from ERP.
        """
        if self.cloud_mode:
            wos = ERPMirrorWorkOrder.query.all()
            return [{
                'wo_id': wo.wo_id,
                'so_number': wo.so_number,
                'description': wo.description,
                'item_number': wo.item_number,
                'status': wo.status,
                'qty': wo.qty,
                'department': wo.department
            } for wo in wos]

        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Corrected query from User:
            # - qty comes from so_detail
            # - statuses are 'Open', 'Completed', 'Canceled'
            query = """
                SELECT 
                    wh.wo_id,
                    wh.source_id,
                    i.item as item_number,
                    i.description,
                    wh.wo_status,
                    sod.qty_ordered,
                    wh.wo_rule as department
                FROM wo_header wh
                LEFT JOIN so_detail sod ON wh.source_id = sod.so_id AND wh.source_seq = sod.sequence
                LEFT JOIN item i ON sod.item_ptr = i.item_ptr
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
                    'qty': row.qty_ordered,
                    'department': row.department
                })
            
            conn.close()
            return wos

        except Exception as e:
            print(f"ERP Connection Error (Open WOs): {e}")
            return []
