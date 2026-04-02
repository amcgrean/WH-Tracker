"""
Work order ERP query methods extracted from ERPService.
"""


class WorkOrdersMixin:
    """Mixin providing work-order-related ERP queries."""

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
                    ON sod.so_id = wh.source_id
                   AND sod.sequence = wh.source_seq
                LEFT JOIN erp_mirror_item i
                    ON i.item_ptr = wh.item_ptr
                LEFT JOIN erp_mirror_item sod_item
                    ON sod_item.item_ptr = sod.item_ptr
                LEFT JOIN erp_mirror_item_branch ib
                    ON (
                        ib.item_ptr = wh.item_ptr
                        OR ib.item_ptr = sod.item_ptr
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
                WHERE wh.source_id = ? AND UPPER(COALESCE(wh.source, '')) = 'SO'
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
                    ON sod.so_id = wh.source_id
                   AND sod.sequence = wh.source_seq
                LEFT JOIN erp_mirror_item i
                    ON i.item_ptr = wh.item_ptr
                LEFT JOIN erp_mirror_item sod_item
                    ON sod_item.item_ptr = sod.item_ptr
                LEFT JOIN erp_mirror_so_header soh
                    ON soh.so_id = wh.source_id
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
                WHERE UPPER(COALESCE(wh.wo_status, '')) NOT IN ('COMPLETED', 'CANCELED', 'C')
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
