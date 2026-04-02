from datetime import datetime, date, timedelta


class DeliveryMixin:
    """Mixin providing delivery tracking methods for ERPService."""

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
                WHERE UPPER(COALESCE(soh.so_status, '')) != 'C'
                  {branch_filter}
                  AND (
                    (soh.expect_date = ?)
                    OR (sh.ship_date = ?)
                    OR (UPPER(COALESCE(soh.so_status, '')) = 'I' AND sh.invoice_date = ?)
                    OR (UPPER(COALESCE(soh.so_status, '')) IN ('K', 'P', 'S') AND (soh.expect_date = ? OR soh.expect_date < ?)) -- Show backlog too but avoid future ones
                  )
                  AND UPPER(COALESCE(soh.sale_type, '')) NOT IN ('DIRECT', 'WILLCALL', 'XINSTALL', 'HOLD')
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
                   AND sh.so_id = soh.so_id
                WHERE soh.is_deleted = false
                  AND CAST(sh.ship_date AS DATE) >= CURRENT_DATE - (:days * INTERVAL '1 day')
                  AND CAST(sh.ship_date AS DATE) < CURRENT_DATE
                  AND UPPER(COALESCE(soh.sale_type, '')) NOT IN ('DIRECT', 'WILLCALL', 'XINSTALL', 'HOLD')
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
                  AND UPPER(COALESCE(soh.sale_type, '')) NOT IN ('DIRECT', 'WILLCALL', 'XINSTALL', 'HOLD')
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
