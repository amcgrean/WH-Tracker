from app.branch_utils import expand_branch


class OrdersMixin:
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
                "UPPER(COALESCE(soh.so_status, '')) = 'K'",
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
                    ON soh.so_id = sod.so_id AND soh.system_id = sod.system_id
                JOIN erp_mirror_item_branch ib
                    ON ib.item_ptr = sod.item_ptr AND sod.system_id = ib.system_id
                LEFT JOIN erp_mirror_cust c
                    ON c.system_id = soh.system_id
                   AND TRIM(c.cust_key) = TRIM(CAST(soh.cust_key AS TEXT))
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON cs.system_id = soh.system_id
                   AND TRIM(cs.cust_key) = TRIM(CAST(soh.cust_key AS TEXT))
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
                WHERE UPPER(COALESCE(soh.so_status, '')) = 'K'
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
                filters.append("soh.so_id IN :so_numbers")
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
                   AND soh.so_id = sod.so_id
                LEFT JOIN erp_mirror_item_branch ib
                    ON ib.system_id = sod.system_id
                   AND ib.item_ptr = sod.item_ptr
                LEFT JOIN erp_mirror_cust c
                    ON c.system_id = soh.system_id AND TRIM(c.cust_key) = TRIM(soh.cust_key)
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON cs.system_id = soh.system_id AND TRIM(cs.cust_key) = TRIM(soh.cust_key)
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

    def get_so_sale_type(self, so_number):
        """
        Lightweight lookup: returns the sale_type for a single SO number.
        Returns uppercase sale_type string, or None if not found.
        """
        if self.central_db_mode:
            rows = self._mirror_query(
                """
                SELECT UPPER(COALESCE(soh.sale_type, '')) AS sale_type
                FROM erp_mirror_so_header soh
                WHERE soh.is_deleted = false
                  AND soh.so_id = :so_number
                LIMIT 1
                """,
                {"so_number": str(so_number)},
            )
            if rows:
                return rows[0]['sale_type'] or None
            return None

        self._require_central_db_for_cloud_mode()
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP 1 UPPER(COALESCE(soh.sale_type, '')) AS sale_type
                FROM so_header soh
                WHERE soh.so_id = ?
                """,
                (so_number,),
            )
            row = cursor.fetchone()
            conn.close()
            return row.sale_type if row else None
        except Exception as e:
            print(f"ERP Connection Error (SO Sale Type): {e}")
            return None

    def get_so_primary_handling_code(self, so_number):
        """
        Lightweight lookup: returns the most common handling_code across
        line items for a single SO.  Returns uppercase string or None.
        """
        if self.central_db_mode:
            rows = self._mirror_query(
                """
                SELECT UPPER(COALESCE(ib.handling_code, '')) AS handling_code,
                       COUNT(*) AS cnt
                FROM erp_mirror_so_detail sod
                LEFT JOIN erp_mirror_item_branch ib
                    ON ib.system_id = sod.system_id AND ib.item_ptr = sod.item_ptr
                WHERE sod.so_id = :so_number
                  AND sod.system_id IN (
                      SELECT soh.system_id
                      FROM erp_mirror_so_header soh
                      WHERE soh.is_deleted = false
                        AND soh.so_id = :so_number
                  )
                  AND COALESCE(ib.handling_code, '') != ''
                GROUP BY UPPER(COALESCE(ib.handling_code, ''))
                ORDER BY cnt DESC
                LIMIT 1
                """,
                {"so_number": str(so_number)},
            )
            if rows:
                return rows[0]['handling_code'] or None
            return None

        self._require_central_db_for_cloud_mode()
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT TOP 1 UPPER(COALESCE(ib.handling_code, '')) AS handling_code,
                       COUNT(*) AS cnt
                FROM so_detail sod
                JOIN item_branch ib ON ib.item_ptr = sod.item_ptr AND sod.system_id = ib.system_id
                WHERE sod.so_id = ?
                  AND sod.system_id IN (
                      SELECT soh.system_id
                      FROM so_header soh
                      WHERE soh.so_id = ?
                  )
                  AND COALESCE(ib.handling_code, '') != ''
                GROUP BY UPPER(COALESCE(ib.handling_code, ''))
                ORDER BY cnt DESC
                """,
                (so_number, so_number),
            )
            row = cursor.fetchone()
            conn.close()
            return row.handling_code if row else None
        except Exception as e:
            print(f"ERP Connection Error (SO Primary Handling Code): {e}")
            return None

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
                    ON c.system_id = soh.system_id
                   AND TRIM(CAST(c.cust_key AS TEXT)) = TRIM(CAST(soh.cust_key AS TEXT))
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON cs.system_id = soh.system_id
                   AND TRIM(CAST(cs.cust_key AS TEXT)) = TRIM(CAST(soh.cust_key AS TEXT))
                    AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                LEFT JOIN erp_mirror_shipments_header sh
                    ON sh.system_id = soh.system_id AND sh.so_id = soh.so_id
                WHERE soh.is_deleted = false
                  AND soh.so_id = :so_number
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
                LEFT JOIN pick_header ph ON soh.so_id = ph.so_id AND soh.system_id = ph.system_id AND UPPER(COALESCE(ph.print_status, '')) = 'PICK TICKET'
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
                WHERE sod.so_id = :so_number
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
