from datetime import datetime, date, timedelta


class CustomersMixin:

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
                    ON ib.item_ptr = i.item_ptr
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

    def get_sales_reports(self, period_days=30, branch="", rep_id=""):
        cache_key = f'sales_reports_{period_days}_{rep_id}' if not branch and not rep_id else None
        if cache_key:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached
        result = self._get_sales_reports_inner(period_days=period_days, branch=branch, rep_id=rep_id)
        if cache_key:
            self._cache_set(cache_key, result)
        return result

    def _get_sales_reports_inner(self, period_days=30, branch="", rep_id=""):
        if self.central_db_mode:
            since = datetime.utcnow() - timedelta(days=period_days)
            params_base: dict = {"since": since}
            branch_clause = ""
            rep_clause = ""
            if branch:
                system_id = self._normalize_branch_system_id(branch)
                if system_id:
                    params_base["branch_id"] = system_id
                    branch_clause = " AND system_id = :branch_id"
            if rep_id:
                params_base["rep_id"] = rep_id
                rep_clause = f" AND {self._rep_filter_clause_bare()}"

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
                  {rep_clause}
                GROUP BY CAST(expect_date AS DATE)
                ORDER BY CAST(expect_date AS DATE)
                """,
                params_base,
            )
            branch_join_clause = ""
            rep_join_clause = ""
            if branch and "branch_id" in params_base:
                branch_join_clause = " AND soh.system_id = :branch_id"
            if rep_id:
                rep_join_clause = f" AND {self._rep_filter_clause()}"
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
                  {rep_join_clause}
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
                  {rep_clause}
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

    def get_customer_details(self, customer_number):
        """Fetch master record for a single customer from erp_mirror_cust."""
        if not customer_number or not self.central_db_mode:
            return {}
        rows = self._mirror_query(
            """
            SELECT
                cust_key, cust_code, cust_name, phone, email,
                balance, credit_limit, terms, branch_code
            FROM erp_mirror_cust
            WHERE is_deleted = false
              AND (TRIM(cust_code) = :cust OR TRIM(cust_key) = :cust)
            LIMIT 1
            """,
            {"cust": customer_number.strip()},
        )
        return dict(rows[0]) if rows else {}

    def get_customer_ship_to_addresses(self, customer_number):
        """Fetch all ship-to addresses for a customer from erp_mirror_cust_shipto."""
        if not customer_number or not self.central_db_mode:
            return []
        rows = self._mirror_query(
            """
            SELECT
                seq_num, shipto_name, address_1, address_2,
                city, state, zip, phone, lat, lon
            FROM erp_mirror_cust_shipto
            WHERE is_deleted = false
              AND TRIM(cust_key) IN (
                  SELECT TRIM(cust_key) FROM erp_mirror_cust
                  WHERE is_deleted = false
                    AND (TRIM(cust_code) = :cust OR TRIM(cust_key) = :cust)
              )
            ORDER BY seq_num
            """,
            {"cust": customer_number.strip()},
        )
        return [dict(row) for row in rows]

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

    def get_distinct_salespeople(self, branch=""):
        """Return distinct sales agent IDs from open sales orders.

        Combines salesperson (sales_agent_1 / account rep) and order_writer
        (sales_agent_3 / order writer) so the dropdown shows actual sales
        agents rather than drivers or other non-sales reps.

        TODO: Replace with a dedicated sales agents table from the ERP mirror
        (e.g. erp_mirror_sales_agents) once that sync is built, so the list
        is authoritative and not derived from order history.
        """
        if self.central_db_mode:
            params: dict = {}
            branch_clause = ""
            if branch:
                system_id = self._normalize_branch_system_id(branch)
                if system_id:
                    params["branch_id"] = system_id
                    branch_clause = "AND soh.system_id = :branch_id"
            rows = self._mirror_query(
                f"""
                SELECT DISTINCT rep_id FROM (
                    SELECT TRIM(soh.salesperson) AS rep_id
                    FROM erp_mirror_so_header soh
                    WHERE soh.is_deleted = false
                      AND COALESCE(soh.salesperson, '') != ''
                      {branch_clause}
                    UNION
                    SELECT TRIM(soh.order_writer) AS rep_id
                    FROM erp_mirror_so_header soh
                    WHERE soh.is_deleted = false
                      AND COALESCE(soh.order_writer, '') != ''
                      {branch_clause}
                ) combined
                ORDER BY rep_id
                """,
                params,
            )
            return [dict(row) for row in rows]

        self._require_central_db_for_cloud_mode()
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            branch_clause = ""
            params_list = []
            if branch:
                system_id = self._normalize_branch_system_id(branch)
                if system_id:
                    branch_clause = "AND soh.system_id = ?"
                    params_list.append(system_id)
            # SQL Server: need branch param twice (once per UNION leg)
            full_params = params_list + params_list
            cursor.execute(
                f"""
                SELECT DISTINCT rep_id FROM (
                    SELECT RTRIM(soh.salesperson) AS rep_id
                    FROM so_header soh
                    WHERE COALESCE(soh.salesperson, '') != ''
                      {branch_clause}
                    UNION
                    SELECT RTRIM(soh.order_writer) AS rep_id
                    FROM so_header soh
                    WHERE COALESCE(soh.order_writer, '') != ''
                      {branch_clause}
                ) combined
                ORDER BY rep_id
                """,
                full_params,
            )
            return [{"rep_id": row.rep_id} for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()
