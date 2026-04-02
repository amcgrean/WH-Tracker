"""ERP sales domain — hub metrics, order status, transactions, invoice lookup."""
from datetime import date, datetime, timedelta


class SalesMixin:
    def get_sales_hub_metrics(self, rep_id=""):
        cache_key = f'hub_metrics_{rep_id}' if rep_id else 'hub_metrics'
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        result = self._get_sales_hub_metrics_inner(rep_id=rep_id)
        return self._cache_set(cache_key, result)


    def _get_sales_hub_metrics_inner(self, rep_id=""):
        if self.central_db_mode:
            today = date.today().isoformat()
            params = {"today": today}
            rep_clause = ""
            if rep_id:
                params["rep_id"] = rep_id
                rep_clause = f" AND {self._rep_filter_clause_bare()}"
            rows = self._mirror_query(
                f"""
                SELECT
                    COUNT(DISTINCT CASE WHEN UPPER(COALESCE(so_status, '')) = 'O' THEN so_id END) AS open_orders_count,
                    COUNT(DISTINCT CASE WHEN CAST(expect_date AS DATE) = :today THEN so_id END) AS total_orders_today
                FROM erp_mirror_so_header
                WHERE is_deleted = false
                {rep_clause}
                """,
                params,
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
                    ON sod.system_id = soh.system_id AND sod.so_id = soh.so_id
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


    def get_sales_order_status(self, q="", limit=100, branch="", open_only=True, rep_id="",
                               status="", date_from="", date_to="", page=1,
                               sale_type="", exclude_sale_types="",
                               customer_code="", salesperson="", shipto_seq=""):
        # Cache unfiltered list for 60 s; skip cache when any filters are active
        has_filters = q or branch or rep_id or status or date_from or date_to or page > 1 or sale_type or exclude_sale_types or customer_code or salesperson or shipto_seq
        cache_key = f'order_status_{limit}' if not has_filters and open_only else None
        if cache_key:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached
        result = self._get_sales_order_status_inner(
            q=q, limit=limit, branch=branch, open_only=open_only, rep_id=rep_id,
            status=status, date_from=date_from, date_to=date_to, page=page,
            sale_type=sale_type, exclude_sale_types=exclude_sale_types,
            customer_code=customer_code, salesperson=salesperson, shipto_seq=shipto_seq,
        )
        if cache_key:
            self._cache_set(cache_key, result)
        return result


    def _get_sales_order_status_inner(self, q="", limit=100, branch="", open_only=True,
                                      rep_id="", status="", date_from="", date_to="", page=1,
                                      sale_type="", exclude_sale_types="",
                                      customer_code="", salesperson="", shipto_seq=""):
        if self.central_db_mode:
            sod_columns = set(self._mirror_columns("erp_mirror_so_detail"))
            if "line_no" in sod_columns:
                line_count_expr = "COUNT(DISTINCT sod.line_no) AS line_count"
            elif "sequence" in sod_columns:
                line_count_expr = "COUNT(DISTINCT sod.sequence) AS line_count"
            else:
                line_count_expr = "COUNT(sod.id) AS line_count"
            params: dict = {"limit": limit}
            clauses = ["soh.is_deleted = false"]
            # Status filtering — explicit status param takes precedence over open_only flag
            if status:
                valid_statuses = [s.strip().upper() for s in status.split(',') if s.strip() and s.strip().isalpha() and len(s.strip()) == 1]
                if valid_statuses:
                    placeholders = ', '.join(f"'{s}'" for s in valid_statuses)
                    clauses.append(f"UPPER(COALESCE(soh.so_status, '')) IN ({placeholders})")
            elif open_only:
                clauses.append("UPPER(COALESCE(soh.so_status, '')) = 'O'")
            if q:
                params["q"] = f"%{q}%"
                clauses.append(
                    "(soh.so_id::text ILIKE :q"
                    " OR COALESCE(c.cust_name, '') ILIKE :q"
                    " OR COALESCE(c.cust_code, '') ILIKE :q"
                    " OR COALESCE(soh.po_number, '') ILIKE :q"
                    " OR COALESCE(soh.reference, '') ILIKE :q)"
                )
            if branch:
                system_id = self._normalize_branch_system_id(branch)
                if system_id:
                    params["branch_id"] = system_id
                    clauses.append("soh.system_id = :branch_id")
            if rep_id:
                params["rep_id"] = rep_id
                clauses.append(self._rep_filter_clause())
            if salesperson:
                params["sp_filter"] = salesperson.strip()
                clauses.append("COALESCE(soh.salesperson, '') = :sp_filter")
            if customer_code:
                params["cust_filter"] = customer_code.strip()
                clauses.append("(TRIM(c.cust_code) = :cust_filter OR TRIM(soh.cust_key) = :cust_filter)")
            if shipto_seq:
                params["shipto_filter"] = shipto_seq.strip()
                clauses.append("TRIM(CAST(soh.shipto_seq_num AS TEXT)) = :shipto_filter")
            if date_from:
                params["date_from"] = date_from
                clauses.append("CAST(soh.expect_date AS DATE) >= :date_from")
            if date_to:
                params["date_to"] = date_to
                clauses.append("CAST(soh.expect_date AS DATE) <= :date_to")
            if sale_type:
                valid_types = [t.strip().upper() for t in sale_type.split(',') if t.strip()]
                if valid_types:
                    type_ph = ', '.join(f"'{t}'" for t in valid_types)
                    clauses.append(f"UPPER(COALESCE(soh.sale_type, '')) IN ({type_ph})")
            if exclude_sale_types:
                valid_excludes = [t.strip().upper() for t in exclude_sale_types.split(',') if t.strip()]
                if valid_excludes:
                    excl_ph = ', '.join(f"'{t}'" for t in valid_excludes)
                    clauses.append(f"UPPER(COALESCE(soh.sale_type, '')) NOT IN ({excl_ph})")
            where_clause = "WHERE " + " AND ".join(clauses)
            page = max(1, page)
            offset = (page - 1) * limit
            params["offset"] = offset
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
                    MAX(COALESCE(soh.salesperson, '')) AS salesperson,
                    {self._order_writer_select()},
                    MAX(COALESCE(soh.po_number, '')) AS po_number,
                    {line_count_expr}
                FROM erp_mirror_so_header soh
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(c.cust_key) = TRIM(soh.cust_key)
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON TRIM(cs.cust_key) = TRIM(soh.cust_key)
                    AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                LEFT JOIN erp_mirror_so_detail sod
                    ON sod.system_id = soh.system_id AND sod.so_id = soh.so_id
                {where_clause}
                GROUP BY soh.system_id, soh.so_id
                ORDER BY MAX(soh.expect_date) DESC NULLS LAST, soh.so_id DESC
                LIMIT :limit OFFSET :offset
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
            params_list = []
            clauses = []
            # Status filtering — explicit status param takes precedence over open_only flag
            if status:
                valid_statuses = [s.strip().upper() for s in status.split(',') if s.strip() and s.strip().isalpha() and len(s.strip()) == 1]
                if valid_statuses:
                    placeholders = ', '.join(f"'{s}'" for s in valid_statuses)
                    clauses.append(f"UPPER(COALESCE(soh.so_status, '')) IN ({placeholders})")
            elif open_only:
                clauses.append("UPPER(COALESCE(soh.so_status, '')) = 'O'")
            if q:
                like = f"%{q}%"
                clauses.append(
                    "(CAST(soh.so_id AS VARCHAR(64)) LIKE ?"
                    " OR COALESCE(c.cust_name, '') LIKE ?"
                    " OR COALESCE(c.cust_code, '') LIKE ?"
                    " OR COALESCE(soh.po_number, '') LIKE ?"
                    " OR COALESCE(soh.reference, '') LIKE ?)"
                )
                params_list.extend([like, like, like, like, like])
            if branch:
                system_id = self._normalize_branch_system_id(branch)
                if system_id:
                    clauses.append("soh.system_id = ?")
                    params_list.append(system_id)
            if rep_id:
                clauses.append(
                    "(COALESCE(soh.salesperson, '') = ? OR COALESCE(soh.order_writer, '') = ?)"
                )
                params_list.extend([rep_id, rep_id])
            if salesperson:
                clauses.append("COALESCE(soh.salesperson, '') = ?")
                params_list.append(salesperson.strip())
            if customer_code:
                clauses.append("(RTRIM(c.cust_code) = ? OR RTRIM(soh.cust_key) = ?)")
                params_list.extend([customer_code.strip(), customer_code.strip()])
            if shipto_seq:
                clauses.append("CAST(soh.shipto_seq_num AS VARCHAR(32)) = ?")
                params_list.append(shipto_seq.strip())
            if date_from:
                clauses.append("CAST(soh.expect_date AS DATE) >= ?")
                params_list.append(date_from)
            if date_to:
                clauses.append("CAST(soh.expect_date AS DATE) <= ?")
                params_list.append(date_to)
            if sale_type:
                valid_types = [t.strip().upper() for t in sale_type.split(',') if t.strip()]
                if valid_types:
                    type_ph = ', '.join(f"'{t}'" for t in valid_types)
                    clauses.append(f"UPPER(COALESCE(soh.sale_type, '')) IN ({type_ph})")
            if exclude_sale_types:
                valid_excludes = [t.strip().upper() for t in exclude_sale_types.split(',') if t.strip()]
                if valid_excludes:
                    excl_ph = ', '.join(f"'{t}'" for t in valid_excludes)
                    clauses.append(f"UPPER(COALESCE(soh.sale_type, '')) NOT IN ({excl_ph})")
            where_clause = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            page = max(1, page)
            offset = (page - 1) * limit

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
                    MAX(COALESCE(soh.salesperson, '')) AS salesperson,
                    {self._order_writer_select()},
                    MAX(COALESCE(soh.po_number, '')) AS po_number,
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
                OFFSET {int(offset)} ROWS FETCH NEXT {int(limit)} ROWS ONLY
                """,
                params_list,
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
                    "salesperson": row.salesperson,
                    "order_writer": row.order_writer,
                    "po_number": row.po_number,
                    "line_count": row.line_count,
                }
                for row in rows
            ]
        finally:
            cursor.close()
            conn.close()


    def get_orders_by_shipment_date(self, date_field="ship_date", date_from="", date_to="",
                                      rep_id="", branch="", limit=100, page=1):
        """Query orders joined with shipments_header, filtering by ship_date or invoice_date."""
        if not self.central_db_mode:
            return []
        sod_columns = set(self._mirror_columns("erp_mirror_so_detail"))
        if "line_no" in sod_columns:
            line_count_expr = "COUNT(DISTINCT sod.line_no) AS line_count"
        elif "sequence" in sod_columns:
            line_count_expr = "COUNT(DISTINCT sod.sequence) AS line_count"
        else:
            line_count_expr = "COUNT(sod.id) AS line_count"

        db_col = "sh.invoice_date" if date_field == "invoice_date" else "sh.ship_date"
        params: dict = {"limit": limit}
        clauses = ["soh.is_deleted = false"]

        if date_from:
            params["date_from"] = date_from
            clauses.append(f"CAST({db_col} AS DATE) >= :date_from")
        if date_to:
            params["date_to"] = date_to
            clauses.append(f"CAST({db_col} AS DATE) <= :date_to")
        if rep_id:
            params["rep_id"] = rep_id
            clauses.append(self._rep_filter_clause())
        if branch:
            system_id = self._normalize_branch_system_id(branch)
            if system_id:
                params["branch_id"] = system_id
                clauses.append("soh.system_id = :branch_id")

        where_clause = "WHERE " + " AND ".join(clauses)
        page = max(1, page)
        offset = (page - 1) * limit
        params["offset"] = offset

        rows = self._mirror_query(
            f"""
            SELECT
                soh.so_id::text AS so_number,
                MAX(c.cust_name) AS customer_name,
                MAX(c.cust_code) AS customer_code,
                MAX(cs.address_1) AS address_1,
                MAX(cs.city) AS city,
                MAX(soh.expect_date) AS expect_date,
                MAX(sh.ship_date) AS ship_date,
                MAX(sh.invoice_date) AS invoice_date,
                MAX(soh.reference) AS reference,
                MAX(soh.so_status) AS so_status,
                '' AS handling_code,
                MAX(soh.sale_type) AS sale_type,
                MAX(COALESCE(soh.ship_via, '')) AS ship_via,
                MAX(COALESCE(soh.salesperson, '')) AS salesperson,
                {self._order_writer_select()},
                MAX(COALESCE(soh.po_number, '')) AS po_number,
                {line_count_expr}
            FROM erp_mirror_so_header soh
            INNER JOIN erp_mirror_shipments_header sh
                ON sh.system_id = soh.system_id AND sh.so_id = soh.so_id
            LEFT JOIN erp_mirror_cust c
                ON TRIM(c.cust_key) = TRIM(soh.cust_key)
            LEFT JOIN erp_mirror_cust_shipto cs
                ON TRIM(cs.cust_key) = TRIM(soh.cust_key)
                AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
            LEFT JOIN erp_mirror_so_detail sod
                ON sod.system_id = soh.system_id AND sod.so_id = soh.so_id
            {where_clause}
            GROUP BY soh.system_id, soh.so_id
            ORDER BY MAX({db_col}) DESC NULLS LAST, soh.so_id DESC
            LIMIT :limit OFFSET :offset
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


    def get_sales_invoice_lookup(self, q="", date_from="", date_to="", status="", limit=50, branch="", rep_id=""):
        if self.central_db_mode:
            params: dict = {"limit": limit}
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
            if rep_id:
                params["rep_id"] = rep_id
                clauses.append(self._rep_filter_clause())

            rows = self._mirror_query(
                f"""
                SELECT
                    soh.so_id::text AS so_number,
                    MAX(c.cust_name) AS customer_name,
                    MAX(c.cust_code) AS customer_code,
                    MAX(COALESCE(sh.invoice_date, soh.expect_date)) AS expect_date,
                    MAX(soh.reference) AS reference,
                    MAX(soh.so_status) AS so_status,
                    MAX(COALESCE(soh.salesperson, '')) AS salesperson,
                    {self._order_writer_select()},
                    MAX(COALESCE(soh.po_number, '')) AS po_number
                FROM erp_mirror_so_header soh
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(c.cust_key) = TRIM(soh.cust_key)
                LEFT JOIN erp_mirror_shipments_header sh
                    ON sh.system_id = soh.system_id AND sh.so_id = soh.so_id
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
            params_list = []
            if q:
                like = f"%{q}%"
                clauses.append(
                    "(CAST(soh.so_id AS VARCHAR(64)) LIKE ?"
                    " OR COALESCE(c.cust_name, '') LIKE ?"
                    " OR COALESCE(c.cust_code, '') LIKE ?)"
                )
                params_list.extend([like, like, like])
            if date_from:
                clauses.append("CAST(COALESCE(sh.invoice_date, soh.expect_date) AS DATE) >= ?")
                params_list.append(date_from)
            if date_to:
                clauses.append("CAST(COALESCE(sh.invoice_date, soh.expect_date) AS DATE) <= ?")
                params_list.append(date_to)
            if branch:
                system_id = self._normalize_branch_system_id(branch)
                if system_id:
                    clauses.append("soh.system_id = ?")
                    params_list.append(system_id)

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
                params_list,
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


    def get_sales_customer_orders(self, customer_number, q="", limit=None, date_from="", date_to="", status="", branch="", page=1, rep_id=""):
        # Cache per-customer full order lists for up to 60 s (skip cache when filtering/paginating)
        cache_key = f'cust_orders_{customer_number}_{limit}' if not (q or date_from or date_to or status or branch or page > 1 or rep_id) else None
        if cache_key:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached
        result = self._get_sales_customer_orders_inner(
            customer_number=customer_number, q=q, limit=limit,
            date_from=date_from, date_to=date_to, status=status, branch=branch, page=page,
            rep_id=rep_id,
        )
        if cache_key:
            self._cache_set(cache_key, result)
        return result


    def _get_sales_customer_orders_inner(self, customer_number, q="", limit=None, date_from="", date_to="", status="", branch="", page=1, rep_id=""):
        if self.central_db_mode:
            sod_columns = set(self._mirror_columns("erp_mirror_so_detail"))
            if "line_no" in sod_columns:
                line_count_expr = "COUNT(DISTINCT sod.line_no) AS line_count"
            elif "sequence" in sod_columns:
                line_count_expr = "COUNT(DISTINCT sod.sequence) AS line_count"
            else:
                line_count_expr = "COUNT(sod.id) AS line_count"
            params: dict = {}
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
            if rep_id:
                params["rep_id"] = rep_id
                clauses.append(self._rep_filter_clause())
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
                     WHERE sod.system_id = soh.system_id AND sod.so_id = soh.so_id
                    ) AS handling_code,
                    MAX(soh.sale_type) AS sale_type,
                    MAX(COALESCE(soh.ship_via, '')) AS ship_via,
                    MAX(COALESCE(soh.salesperson, '')) AS salesperson,
                    {self._order_writer_select()},
                    MAX(COALESCE(soh.po_number, '')) AS po_number,
                    {line_count_expr}
                FROM erp_mirror_so_header soh
                LEFT JOIN erp_mirror_cust c
                    ON TRIM(c.cust_key) = TRIM(soh.cust_key)
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON TRIM(cs.cust_key) = TRIM(soh.cust_key)
                    AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                LEFT JOIN erp_mirror_so_detail sod
                    ON sod.system_id = soh.system_id AND sod.so_id = soh.so_id
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
