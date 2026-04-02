from datetime import datetime


class PicksMixin:
    """Pick/warehouse methods extracted from ERPService.

    Combined with ERPServiceBase via multiple inheritance so all
    self._mirror_query, self._cache_get, etc. calls resolve at runtime.
    """

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
                        sh.so_id,
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
                    WHERE sh.invoice_date >= CURRENT_DATE - INTERVAL '180 days'
                       OR sh.ship_date    >= CURRENT_DATE - INTERVAL '180 days'
                       OR UPPER(COALESCE(sh.status_flag, '')) NOT IN ('C', 'X')
                    GROUP BY sh.system_id, sh.so_id
                ),
                pick_rollup AS (
                    SELECT
                        pd.system_id,
                        pd.tran_id AS so_id,
                        MAX(ph.created_date) AS created_date,
                        MAX(ph.created_time) AS created_time
                    FROM erp_mirror_pick_header ph
                    JOIN erp_mirror_pick_detail pd
                        ON ph.pick_id = pd.pick_id
                       AND ph.system_id = pd.system_id
                    WHERE UPPER(COALESCE(ph.print_status, '')) = 'PICK TICKET'
                      AND UPPER(COALESCE(pd.tran_type, '')) = 'SO'
                      AND ph.created_date >= CURRENT_DATE - INTERVAL '30 days'
                    GROUP BY pd.system_id, pd.tran_id
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
                   AND soh.so_id = sod.so_id
                LEFT JOIN erp_mirror_item i
                    ON i.item_ptr = sod.item_ptr
                LEFT JOIN erp_mirror_item_branch ib
                    ON ib.system_id = sod.system_id
                   AND ib.item_ptr = sod.item_ptr
                LEFT JOIN erp_mirror_cust c
                    ON c.system_id = soh.system_id AND TRIM(c.cust_key) = TRIM(soh.cust_key)
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON cs.system_id = soh.system_id AND TRIM(cs.cust_key) = TRIM(soh.cust_key)
                   AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                LEFT JOIN shipment_rollup sh
                    ON sh.system_id = soh.system_id
                   AND sh.so_id = soh.so_id
                LEFT JOIN pick_rollup ph
                    ON ph.system_id = soh.system_id
                   AND ph.so_id = soh.so_id
                WHERE soh.is_deleted = false
                  AND UPPER(COALESCE(soh.so_status, '')) != 'C'
                  AND (
                    (UPPER(COALESCE(soh.so_status, '')) IN ('K', 'P', 'S'))
                    OR (UPPER(COALESCE(soh.so_status, '')) = 'I' AND CAST(sh.invoice_date AS DATE) = :today)
                    OR (CAST(soh.expect_date AS DATE) = :today)
                    OR (CAST(sh.ship_date AS DATE) = :today)
                  )
                  AND UPPER(COALESCE(soh.sale_type, '')) NOT IN ('DIRECT', 'WILLCALL', 'XINSTALL', 'HOLD')
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
                    WHERE UPPER(COALESCE(ph.print_status, '')) = 'PICK TICKET' AND UPPER(COALESCE(pd.tran_type, '')) = 'SO'
                    GROUP BY pd.tran_id, pd.system_id
                ) ph ON soh.so_id = ph.so_id AND soh.system_id = ph.system_id
                WHERE UPPER(COALESCE(soh.so_status, '')) != 'C'
                  AND (
                    (UPPER(COALESCE(soh.so_status, '')) IN ('K', 'P', 'S'))
                    OR (UPPER(COALESCE(soh.so_status, '')) = 'I' AND sh.invoice_date = '{today}')
                    OR (soh.expect_date = '{today}')
                    OR (sh.ship_date = '{today}')
                  )
                  AND UPPER(COALESCE(soh.sale_type, '')) NOT IN ('DIRECT', 'WILLCALL', 'XINSTALL', 'HOLD')
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

    # ------------------------------------------------------------------
    # Lightweight COUNT-only methods for the homepage dashboard
    # ------------------------------------------------------------------

    def get_open_picks_count(self):
        """Return open pick total count (distinct SOs) and handling-code
        breakdown without fetching full row data.  Cached for 60 seconds.

        NOTE: Counts distinct sales orders, not individual pick lines.
        The handling breakdown counts distinct SOs per handling code (an SO
        with items in multiple handling codes appears in each category).
        """
        cache_key = 'open_picks_count'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        _PICK_STATUS_FILTER = """
            UPPER(COALESCE(soh.so_status, '')) != 'C'
            AND (
              (UPPER(COALESCE(soh.so_status, '')) IN ('K', 'P', 'S'))
              OR (UPPER(COALESCE(soh.so_status, '')) = 'I' AND CAST(sh.invoice_date AS DATE) = {today_param})
              OR (CAST(soh.expect_date AS DATE) = {today_param})
              OR (CAST(sh.ship_date AS DATE) = {today_param})
            )
            AND UPPER(COALESCE(soh.sale_type, '')) NOT IN ('DIRECT', 'WILLCALL', 'XINSTALL', 'HOLD')
        """

        if self.central_db_mode:
            today = datetime.now().strftime('%Y-%m-%d')

            # Total: count distinct SOs (no detail/item join needed)
            total_rows = self._mirror_query(
                """
                SELECT COUNT(DISTINCT (soh.system_id, soh.so_id)) AS cnt
                FROM erp_mirror_so_header soh
                LEFT JOIN erp_mirror_shipments_header sh
                    ON sh.system_id = soh.system_id AND sh.so_id = soh.so_id
                WHERE soh.is_deleted = false
                  AND """ + _PICK_STATUS_FILTER.format(today_param=':today') + """
                """,
                {"today": today},
            )
            total = int(total_rows[0]['cnt']) if total_rows else 0

            # Breakdown: distinct SOs per handling code
            rows = self._mirror_query(
                """
                SELECT
                    UPPER(COALESCE(ib.handling_code, '')) AS handling_code,
                    COUNT(DISTINCT (sod.system_id, sod.so_id)) AS cnt
                FROM erp_mirror_so_detail sod
                JOIN erp_mirror_so_header soh
                    ON soh.system_id = sod.system_id AND soh.so_id = sod.so_id
                LEFT JOIN erp_mirror_item_branch ib
                    ON ib.system_id = sod.system_id AND ib.item_ptr = sod.item_ptr
                LEFT JOIN erp_mirror_shipments_header sh
                    ON sh.system_id = soh.system_id AND sh.so_id = soh.so_id
                WHERE soh.is_deleted = false
                  AND """ + _PICK_STATUS_FILTER.format(today_param=':today') + """
                GROUP BY UPPER(COALESCE(ib.handling_code, ''))
                """,
                {"today": today},
            )
            handling = {}
            for r in rows:
                code = (r['handling_code'] or '').strip() or '—'
                handling[code] = int(r['cnt'])
            result = {'total': total, 'handling_breakdown': dict(sorted(handling.items()))}
            return self._cache_set(cache_key, result)

        self._require_central_db_for_cloud_mode()
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            today = datetime.now().strftime('%Y-%m-%d')

            # Total: count distinct SOs (no detail/item join needed)
            cursor.execute(f"""
                SELECT COUNT(DISTINCT CONCAT(soh.system_id, '|', soh.so_id)) AS cnt
                FROM so_header soh
                LEFT JOIN (
                    SELECT so_id, system_id,
                           MAX(invoice_date) as invoice_date,
                           MAX(ship_date) as ship_date
                    FROM shipments_header GROUP BY so_id, system_id
                ) sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
                WHERE """ + _PICK_STATUS_FILTER.format(today_param=f"'{today}'") + """
            """)
            total_row = cursor.fetchone()
            total = int(total_row.cnt) if total_row else 0

            # Breakdown: distinct SOs per handling code
            cursor.execute(f"""
                SELECT
                    UPPER(COALESCE(ib.handling_code, '')) AS handling_code,
                    COUNT(DISTINCT CONCAT(sod.system_id, '|', sod.so_id)) AS cnt
                FROM so_detail sod
                JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id
                JOIN item_branch ib ON ib.item_ptr = sod.item_ptr AND sod.system_id = ib.system_id
                LEFT JOIN (
                    SELECT so_id, system_id,
                           MAX(invoice_date) as invoice_date,
                           MAX(ship_date) as ship_date
                    FROM shipments_header GROUP BY so_id, system_id
                ) sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
                WHERE """ + _PICK_STATUS_FILTER.format(today_param=f"'{today}'") + """
                GROUP BY UPPER(COALESCE(ib.handling_code, ''))
            """)
            handling = {}
            for row in cursor.fetchall():
                code = (row.handling_code or '').strip() or '—'
                handling[code] = int(row.cnt)
            conn.close()
            result = {'total': total, 'handling_breakdown': dict(sorted(handling.items()))}
            return self._cache_set(cache_key, result)
        except Exception as e:
            print(f"ERP Connection Error (open_picks_count): {e}")
            return {'total': 0, 'handling_breakdown': {}}

    def get_open_work_orders_count(self):
        """Return count of open work orders.  Cached for 60 seconds."""
        cache_key = 'open_wo_count'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        if self.central_db_mode:
            rows = self._mirror_query(
                """
                SELECT COUNT(*) AS cnt
                FROM erp_mirror_wo_header wh
                WHERE wh.is_deleted = false
                  AND UPPER(COALESCE(wh.wo_status, '')) NOT IN ('COMPLETED', 'CANCELED', 'C')
                """
            )
            count = int(rows[0]['cnt']) if rows else 0
            return self._cache_set(cache_key, count)

        self._require_central_db_for_cloud_mode()
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) AS cnt
                FROM wo_header wh
                WHERE UPPER(COALESCE(wh.wo_status, '')) NOT IN ('COMPLETED', 'CANCELED', 'C')
            """)
            row = cursor.fetchone()
            conn.close()
            count = int(row.cnt) if row else 0
            return self._cache_set(cache_key, count)
        except Exception as e:
            print(f"ERP Connection Error (open_wo_count): {e}")
            return 0

    def get_delivery_count(self, branch_id=None):
        """Return count of today's deliveries.  Cached for 60 seconds."""
        cache_key = f'delivery_count_{branch_id or "all"}'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

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
                SELECT COUNT(DISTINCT (soh.system_id, soh.so_id)) AS cnt
                FROM erp_mirror_so_header soh
                LEFT JOIN erp_mirror_shipments_header sh
                    ON sh.system_id = soh.system_id AND sh.so_id = soh.so_id
                WHERE soh.is_deleted = false
                  AND UPPER(COALESCE(soh.so_status, '')) != 'C'
                  {branch_filter}
                  AND (
                    (CAST(soh.expect_date AS DATE) = :today)
                    OR (CAST(sh.ship_date AS DATE) = :today)
                    OR (UPPER(COALESCE(soh.so_status, '')) = 'I' AND CAST(sh.invoice_date AS DATE) = :today)
                    OR (UPPER(COALESCE(soh.so_status, '')) IN ('K', 'P', 'S') AND (CAST(soh.expect_date AS DATE) = :today OR CAST(soh.expect_date AS DATE) < :today))
                  )
                  AND UPPER(COALESCE(soh.sale_type, '')) NOT IN ('DIRECT', 'WILLCALL', 'XINSTALL', 'HOLD')
                """,
                params,
            )
            count = int(rows[0]['cnt']) if rows else 0
            return self._cache_set(cache_key, count)

        self._require_central_db_for_cloud_mode()
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            today = datetime.now().strftime('%Y-%m-%d')
            query_params = []
            branch_filter = ""
            system_id = self._normalize_branch_system_id(branch_id)
            if system_id:
                branch_filter = " AND soh.system_id = ?"
                query_params.append(system_id)

            cursor.execute(f"""
                SELECT COUNT(DISTINCT CAST(soh.system_id AS VARCHAR) + '-' + CAST(soh.so_id AS VARCHAR)) AS cnt
                FROM so_header soh
                LEFT JOIN shipments_header sh ON soh.so_id = sh.so_id AND soh.system_id = sh.system_id
                WHERE UPPER(COALESCE(soh.so_status, '')) != 'C'
                  {branch_filter}
                  AND (
                    (soh.expect_date = ?)
                    OR (sh.ship_date = ?)
                    OR (UPPER(COALESCE(soh.so_status, '')) = 'I' AND sh.invoice_date = ?)
                    OR (UPPER(COALESCE(soh.so_status, '')) IN ('K', 'P', 'S') AND (soh.expect_date = ? OR soh.expect_date < ?))
                  )
                  AND UPPER(COALESCE(soh.sale_type, '')) NOT IN ('DIRECT', 'WILLCALL', 'XINSTALL', 'HOLD')
            """, query_params + [today, today, today, today, today])
            row = cursor.fetchone()
            conn.close()
            count = int(row.cnt) if row else 0
            return self._cache_set(cache_key, count)
        except Exception as e:
            print(f"ERP Connection Error (delivery_count): {e}")
            return 0
