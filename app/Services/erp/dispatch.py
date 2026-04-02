"""ERP dispatch domain — stops, delivery orders, shipment lines, AR summary."""
from datetime import date, timedelta

from app.branch_utils import expand_branch_filter
from app.extensions import db


class DispatchMixin:
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
                types = [item.strip().upper() for item in sale_types.split(",") if item.strip()]
                if types:
                    filters.append("UPPER(COALESCE(soh.sale_type, '')) IN :sale_types")
                    params["sale_types"] = types

            if status_filter:
                statuses = [item.strip().upper() for item in status_filter.split(",") if item.strip()]
                if statuses:
                    filters.append("UPPER(COALESCE(soh.so_status, '')) IN :statuses")
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
                    ON c.system_id = soh.system_id
                   AND c.is_deleted = false
                   AND TRIM(CAST(c.cust_key AS TEXT)) = TRIM(CAST(soh.cust_key AS TEXT))
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON cs.system_id = soh.system_id
                   AND cs.is_deleted = false
                   AND TRIM(CAST(cs.cust_key AS TEXT)) = TRIM(CAST(soh.cust_key AS TEXT))
                    AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                LEFT JOIN erp_mirror_shipments_header sh
                    ON sh.system_id = soh.system_id AND sh.so_id = soh.so_id AND sh.is_deleted = false
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
                types = [item.strip().upper() for item in sale_types.split(",") if item.strip()]
                if types:
                    filters.append(f"UPPER(COALESCE(hdr.sale_type, '')) IN ({','.join('?' for _ in types)})")
                    params.extend(types)

            if status_filter:
                statuses = [item.strip().upper() for item in status_filter.split(",") if item.strip()]
                if statuses:
                    filters.append(f"UPPER(COALESCE(hdr.so_status, '')) IN ({','.join('?' for _ in statuses)})")
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


    def get_enriched_dispatch_stops(
        self,
        start,
        end,
        sale_types=None,
        status_filter=None,
        route_id=None,
        driver=None,
        include_no_gps=False,
        branches=None,
    ):
        """Enhanced version of get_dispatch_stops that adds order value,
        customer credit, pick status, work order flags, and local route
        assignment info.  Only works in central_db (cloud mirror) mode."""
        if not self.central_db_mode:
            # Fall back to base stops for legacy mode
            return self.get_dispatch_stops(
                start, end, sale_types, status_filter, route_id, driver,
                include_no_gps, branches,
            )

        # Get base stops
        base_stops = self.get_dispatch_stops(
            start, end, sale_types, status_filter, route_id, driver,
            include_no_gps, branches,
        )
        if not base_stops:
            return base_stops

        so_ids = list({str(s["id"]) for s in base_stops if s.get("id")})
        if not so_ids:
            return base_stops

        # --- Enrich: order value from so_detail ---
        try:
            value_rows = self._mirror_query(
                """
                SELECT CAST(so_id AS TEXT) AS so_id,
                       SUM(COALESCE(price, 0) * COALESCE(qty_ordered, 0)) AS order_value
                FROM erp_mirror_so_detail
                WHERE is_deleted = false AND CAST(so_id AS TEXT) IN :so_ids
                GROUP BY so_id
                """,
                {"so_ids": so_ids},
                expanding={"so_ids"},
            )
            value_map = {str(r["so_id"]): float(r["order_value"] or 0) for r in value_rows}
        except Exception:
            value_map = {}

        # --- Enrich: customer credit info ---
        cust_keys = list({s.get("customer_code") for s in base_stops if s.get("customer_code")})
        cust_credit_map = {}
        if cust_keys:
            try:
                credit_rows = self._mirror_query(
                    """
                    SELECT cust_key, cust_name, balance, credit_limit, credit_account
                    FROM erp_mirror_cust
                    WHERE is_deleted = false AND cust_code IN :cust_keys
                    """,
                    {"cust_keys": cust_keys},
                    expanding={"cust_keys"},
                )
                for r in credit_rows:
                    cust_credit_map[r["cust_key"]] = {
                        "customer_balance": float(r["balance"] or 0),
                        "credit_limit": float(r["credit_limit"] or 0),
                        "credit_hold": (float(r["balance"] or 0) > float(r["credit_limit"] or 0)) if r["credit_limit"] else False,
                    }
            except Exception:
                pass

        # --- Enrich: work order flags ---
        try:
            wo_rows = self._mirror_query(
                """
                SELECT DISTINCT CAST(source_id AS TEXT) AS so_id
                FROM erp_mirror_wo_header
                WHERE is_deleted = false AND CAST(source_id AS TEXT) IN :so_ids
                """,
                {"so_ids": so_ids},
                expanding={"so_ids"},
            )
            wo_set = {str(r["so_id"]) for r in wo_rows}
        except Exception:
            wo_set = set()

        # --- Enrich: SO header fields (ship_via, po_number, salesperson, promise_date) ---
        try:
            so_rows = self._mirror_query(
                """
                SELECT CAST(so_id AS TEXT) AS so_id, ship_via, po_number, salesperson,
                       promise_date, cust_key
                FROM erp_mirror_so_header
                WHERE is_deleted = false AND CAST(so_id AS TEXT) IN :so_ids
                """,
                {"so_ids": so_ids},
                expanding={"so_ids"},
            )
            so_map = {}
            for r in so_rows:
                so_map[str(r["so_id"])] = {
                    "ship_via": r.get("ship_via"),
                    "po_number": r.get("po_number"),
                    "salesperson": r.get("salesperson"),
                    "promise_date": r["promise_date"].isoformat() if hasattr(r.get("promise_date"), "isoformat") else r.get("promise_date"),
                    "cust_key": r.get("cust_key"),
                }
        except Exception:
            so_map = {}

        # --- Enrich: local route assignments ---
        from app.Models.dispatch_models import DispatchRouteStop, DispatchRoute
        try:
            assigned_stops = (
                db.session.query(
                    DispatchRouteStop.so_id,
                    DispatchRoute.id.label("local_route_id"),
                    DispatchRoute.route_name.label("local_route_name"),
                )
                .join(DispatchRoute, DispatchRouteStop.route_id == DispatchRoute.id)
                .filter(DispatchRoute.route_date >= start, DispatchRoute.route_date <= end)
                .all()
            )
            route_assign_map = {
                str(s.so_id): {
                    "local_route_id": s.local_route_id,
                    "local_route_name": s.local_route_name,
                    "route_assigned": True,
                }
                for s in assigned_stops
            }
        except Exception:
            route_assign_map = {}

        # --- Merge enrichments into base stops ---
        for stop in base_stops:
            sid = str(stop.get("id", ""))

            # Order value
            stop["order_value"] = round(value_map.get(sid, 0), 2)

            # Work orders
            stop["has_work_orders"] = sid in wo_set

            # SO header fields
            so_info = so_map.get(sid, {})
            stop["ship_via"] = so_info.get("ship_via")
            stop["po_number"] = so_info.get("po_number")
            stop["salesperson"] = so_info.get("salesperson")
            stop["promise_date"] = so_info.get("promise_date")

            # Customer credit
            cust_key = so_info.get("cust_key")
            credit_info = cust_credit_map.get(cust_key, {})
            stop["customer_balance"] = credit_info.get("customer_balance")
            stop["credit_limit"] = credit_info.get("credit_limit")
            stop["credit_hold"] = credit_info.get("credit_hold", False)

            # Local route assignment
            route_info = route_assign_map.get(sid, {})
            stop["route_assigned"] = route_info.get("route_assigned", False)
            stop["local_route_id"] = route_info.get("local_route_id")
            stop["local_route_name"] = route_info.get("local_route_name")

        return base_stops


    def get_customer_ar_summary(self, cust_key):
        """Get AR aging buckets for a customer."""
        if not self.central_db_mode:
            return {}
        from datetime import timedelta
        now = date.today()
        try:
            rows = self._mirror_query(
                """
                SELECT ref_num, ref_date, open_amt, open_flag
                FROM erp_mirror_aropen
                WHERE is_deleted = false AND cust_key = :cust_key AND open_flag = true
                """,
                {"cust_key": cust_key},
            )
            buckets = {"current": 0, "over_30": 0, "over_60": 0, "over_90": 0, "total": 0}
            for r in rows:
                amt = float(r.get("open_amt") or 0)
                ref_date = r.get("ref_date")
                if ref_date and hasattr(ref_date, "date"):
                    ref_date = ref_date.date()
                days = (now - ref_date).days if ref_date else 0
                if days > 90:
                    buckets["over_90"] += amt
                elif days > 60:
                    buckets["over_60"] += amt
                elif days > 30:
                    buckets["over_30"] += amt
                else:
                    buckets["current"] += amt
                buckets["total"] += amt
            for k in buckets:
                buckets[k] = round(buckets[k], 2)
            return buckets
        except Exception:
            return {}


    def get_order_work_orders(self, so_id):
        """Get work orders linked to a sales order."""
        if not self.central_db_mode:
            return []
        try:
            rows = self._mirror_query(
                """
                SELECT wo_id, wo_status, item_ptr, qty, department, branch_code
                FROM erp_mirror_wo_header
                WHERE is_deleted = false AND CAST(source_id AS TEXT) = :so_id
                ORDER BY wo_id
                """,
                {"so_id": str(so_id)},
            )
            return [
                {
                    "wo_id": r["wo_id"],
                    "status": r["wo_status"],
                    "item": r["item_ptr"],
                    "qty": float(r["qty"]) if r.get("qty") else None,
                    "department": r["department"],
                    "branch": r["branch_code"],
                }
                for r in rows
            ]
        except Exception:
            return []


    def get_order_timeline(self, so_id):
        """Get audit events for an order to build a status timeline."""
        try:
            from app.Models.models import AuditEvent
            events = (
                AuditEvent.query
                .filter_by(so_number=str(so_id))
                .order_by(AuditEvent.occurred_at)
                .all()
            )
            return [
                {
                    "event_type": e.event_type,
                    "entity_type": e.entity_type,
                    "notes": e.notes,
                    "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
                }
                for e in events
            ]
        except Exception:
            return []


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
                    ON soh.system_id = sod.system_id AND soh.so_id = sod.so_id
                LEFT JOIN erp_mirror_cust c
                    ON c.system_id = soh.system_id AND TRIM(c.cust_key) = TRIM(soh.cust_key)
                LEFT JOIN erp_mirror_cust_shipto cs
                    ON cs.system_id = soh.system_id AND TRIM(cs.cust_key) = TRIM(soh.cust_key) AND TRIM(CAST(cs.seq_num AS TEXT)) = TRIM(CAST(soh.shipto_seq_num AS TEXT))
                LEFT JOIN erp_mirror_shipments_header sh
                    ON sh.system_id = soh.system_id AND sh.so_id = soh.so_id
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
                WHERE UPPER(COALESCE(soh.so_status, '')) = 'K'
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
