import csv
import os
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
import qrcode
from sqlalchemy import func, text

from app.branch_utils import expand_branch_filter
from app.extensions import db
from app.runtime_settings import build_sql_connection_strings, sql_connection_configured

try:
    import pyodbc
except (ImportError, OSError):
    pyodbc = None


class DispatchService:
    def __init__(self) -> None:
        self._gps_cache: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None
        self._samsara_cache: Dict[str, Any] = {"ts": 0.0, "data": None}

    def using_db(self) -> bool:
        return sql_connection_configured()

    def get_branch_choices(self) -> List[Dict[str, str]]:
        raw = os.getenv("SAMSARA_BRANCH_TAGS_JSON", "")
        if raw:
            try:
                import json

                data = json.loads(raw)
                return sorted(
                    [{"code": str(key), "name": str(key)} for key in data.keys()],
                    key=lambda item: item["code"],
                )
            except Exception:
                pass
        return [
            {"code": "20GR", "name": "20GR"},
            {"code": "25BW", "name": "25BW"},
            {"code": "10FD", "name": "10FD"},
            {"code": "40CV", "name": "40CV"},
            {"code": "GRIMES", "name": "Grimes Area"},
        ]

    def _connect(self):
        if pyodbc is None:
            raise RuntimeError("pyodbc is not installed.")
        variants = build_sql_connection_strings()
        if not variants:
            raise RuntimeError("Missing SQL Server config for dispatch service.")

        last_error = None
        for connection_string in variants:
            try:
                return pyodbc.connect(connection_string)
            except Exception as exc:
                last_error = exc
        raise last_error

    def _normalize_header(self, value: str) -> str:
        return (value or "").strip().lower().replace(" ", "").replace("_", "")

    def _load_gps_map(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
        if self._gps_cache is not None:
            return self._gps_cache

        path = os.environ.get("GPS_CSV_PATH")
        gps: Dict[Tuple[str, str], Dict[str, Any]] = {}
        if not path or not os.path.exists(path):
            self._gps_cache = gps
            return gps

        with open(path, "r", encoding="utf-8", newline="") as handle:
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

            def idx(*candidates: str, default=None):
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

                parts = [value for value in [sval(addr_i), sval(city_i), sval(state_i), sval(zip_i)] if value]
                gps[(cust, ship)] = {
                    "lat": fnum(lat_i),
                    "lon": fnum(lon_i),
                    "address": " ".join(parts).strip(),
                }

        self._gps_cache = gps
        return gps

    def _aggregate_shipment_details(self, so_ids: List[Any]) -> Dict[Tuple[Any, Any], Dict[str, Any]]:
        if not so_ids:
            return {}

        conn = self._connect()
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in so_ids)

        try:
            cur.execute(f"SELECT * FROM SHIPMENTS_DETAIL WHERE so_id IN ({placeholders})", so_ids)
            rows = cur.fetchall()
            if not rows:
                return {}

            cols = [col[0].lower() for col in cur.description]

            def pick(*candidates: str):
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
            aggregates: Dict[Tuple[Any, Any], Dict[str, Any]] = {}

            for row in rows:
                so_id = row[index[so_col]]
                shipment_num = row[index[ship_col]] if ship_col else None
                key = (so_id, shipment_num)
                info = aggregates.setdefault(key, {"item_count": 0, "total_weight": 0.0})

                qty_value = None
                if qty_shipped_col:
                    qty_value = row[index[qty_shipped_col]]
                if (qty_value is None or float(qty_value or 0) == 0) and qty_ordered_col:
                    qty_value = row[index[qty_ordered_col]]
                if qty_shipped_col or qty_ordered_col:
                    if float(qty_value or 0) > 0:
                        info["item_count"] += 1
                else:
                    info["item_count"] += 1

                if weight_col:
                    try:
                        info["total_weight"] += float(row[index[weight_col]] or 0)
                    except Exception:
                        pass

            for value in aggregates.values():
                value["total_weight"] = round(value["total_weight"], 2)
            return aggregates
        finally:
            cur.close()
            conn.close()

    def get_stops(
        self,
        start: date,
        end: date,
        sale_types: Optional[str] = None,
        status_filter: Optional[str] = None,
        route_id: Optional[str] = None,
        driver: Optional[str] = None,
        include_no_gps: bool = False,
        branches: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conn = self._connect()
        cur = conn.cursor()

        filters: List[str] = [
            "("
            " (UPPER(hdr.[type]) = 'CM' AND UPPER(hdr.so_status) NOT IN ('I','C','X','CAN','CANCEL','CANCELED','CN','VOID'))"
            " OR "
            " (UPPER(hdr.[type]) <> 'CM' AND COALESCE(sh.expect_date, hdr.expect_date) BETWEEN ? AND ?)"
            ")",
            "UPPER(hdr.so_status) NOT IN ('I','C','X','CAN','CANCEL','CANCELED','CN','VOID')",
            "UPPER(COALESCE(hdr.sale_type,'')) NOT IN ('DIRECT','WILLCALL','HOLD')",
        ]
        params: List[Any] = [start, end]

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

        sql = f"""
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

        try:
            cur.execute(sql, params)
            rows = cur.fetchall()
            cols = [col[0] for col in cur.description]
        finally:
            cur.close()
            conn.close()

        results: List[Dict[str, Any]] = []
        for row in rows:
            obj = dict(zip(cols, row))
            if hasattr(obj.get("expected_date"), "isoformat"):
                obj["expected_date"] = obj["expected_date"].isoformat()
            results.append(obj)

        gps_map = self._load_gps_map()
        for obj in results:
            if not obj.get("shipto_name") and obj.get("customer_name"):
                obj["shipto_name"] = obj["customer_name"]
            if not obj.get("address") and obj.get("shipto_address"):
                obj["address"] = obj["shipto_address"]
            customer = (obj.get("CustomerCode") or "").strip()
            ship_to = (obj.get("ShipToNumber") or "").strip()
            hit = gps_map.get((customer, ship_to))
            if hit and hit.get("lat") is not None and hit.get("lon") is not None:
                obj["lat"] = hit["lat"]
                obj["lon"] = hit["lon"]
                if not obj.get("address"):
                    obj["address"] = hit.get("address")

        if not include_no_gps:
            results = [item for item in results if item.get("lat") is not None and item.get("lon") is not None]

        for obj in results:
            obj.pop("CustomerCode", None)
            obj.pop("ShipToNumber", None)
            obj.pop("shipto_address", None)

        try:
            so_ids = [item.get("id") for item in results if item.get("id") is not None]
            aggregates = self._aggregate_shipment_details(so_ids)
            for item in results:
                key = (item.get("id"), item.get("shipment_num"))
                info = aggregates.get(key) or aggregates.get((item.get("id"), None))
                if info:
                    item["item_count"] = info.get("item_count")
                    item["total_weight"] = info.get("total_weight")
        except Exception:
            pass

        return results

    def _table_columns(self, cursor, table_name: str) -> List[str]:
        cols: List[str] = []
        try:
            for row in cursor.columns(table=table_name):
                cols.append(row.column_name)
        except Exception:
            return []
        return cols

    def _pick_column(self, cols: List[str], *candidates: str) -> Optional[str]:
        lower = {col.lower(): col for col in cols}
        for candidate in candidates:
            if candidate.lower() in lower:
                return lower[candidate.lower()]
        return None

    def get_shipment_lines(
        self, so_id: int, shipment_num: Optional[int] = None, limit: int = 200
    ) -> List[Dict[str, Any]]:
        conn = self._connect()
        cur = conn.cursor()
        try:
            cols = self._table_columns(cur, "SHIPMENTS_DETAIL")
            if not cols:
                return []

            so_col = self._pick_column(cols, "so_id", "soid", "so") or "so_id"
            shipment_col = self._pick_column(cols, "shipment_num", "shipment_id", "release_no", "shipment_no")
            line_col = self._pick_column(cols, "line_no", "line", "seq", "sequence", "detail_seq")
            item_col = self._pick_column(cols, "item_id", "item_no", "sku", "merch_id", "prod_id")
            desc_col = self._pick_column(cols, "item_description", "description", "item_desc", "descr")
            qty_ordered_col = self._pick_column(cols, "qty_ordered", "qty", "ordered_qty", "qty_to_ship")
            qty_shipped_col = self._pick_column(cols, "qty_shipped", "shipped_qty", "qty_ship", "qty_delivered")
            uom_col = self._pick_column(cols, "uom", "unit", "unit_of_measure")
            weight_col = self._pick_column(cols, "weight", "line_weight", "wt")

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
            params: List[Any] = [so_id]
            if shipment_num is not None and shipment_col:
                where += f" AND {shipment_col} = ?"
                params.append(shipment_num)

            query = f"SELECT {', '.join(select_parts)} FROM SHIPMENTS_DETAIL WHERE {where} ORDER BY {order_by}"
            cur.execute(query, params)
            names = [col[0] for col in cur.description]
            rows = cur.fetchall()
            return [dict(zip(names, row)) for row in rows][:limit]
        finally:
            cur.close()
            conn.close()

    # ------------------------------------------------------------------
    # Route CRUD
    # ------------------------------------------------------------------

    def get_routes_for_date(
        self, route_date: date, branch: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        from app.Models.dispatch_models import DispatchRoute

        q = DispatchRoute.query.filter_by(route_date=route_date)
        if branch:
            branches = self._expand_branch(branch)
            q = q.filter(DispatchRoute.branch_code.in_(branches))
        routes = q.order_by(DispatchRoute.route_name).all()
        return [r.to_dict() for r in routes]

    def create_route(
        self,
        route_date: date,
        route_name: str,
        branch_code: str,
        driver_name: Optional[str] = None,
        truck_id: Optional[str] = None,
        notes: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        from app.Models.dispatch_models import DispatchRoute

        route = DispatchRoute(
            route_date=route_date,
            route_name=route_name,
            branch_code=branch_code,
            driver_name=driver_name,
            truck_id=truck_id,
            notes=notes,
            created_by=user_id,
        )
        db.session.add(route)
        db.session.commit()
        return route.to_dict()

    def update_route(self, route_id: int, **kwargs) -> Optional[Dict[str, Any]]:
        from app.Models.dispatch_models import DispatchRoute

        route = DispatchRoute.query.get(route_id)
        if not route:
            return None
        allowed = (
            "route_name",
            "driver_name",
            "truck_id",
            "status",
            "notes",
            "branch_code",
        )
        for key, value in kwargs.items():
            if key in allowed:
                setattr(route, key, value)
        db.session.commit()
        return route.to_dict()

    def delete_route(self, route_id: int) -> bool:
        from app.Models.dispatch_models import DispatchRoute

        route = DispatchRoute.query.get(route_id)
        if not route:
            return False
        db.session.delete(route)
        db.session.commit()
        return True

    # ------------------------------------------------------------------
    # Route Stop CRUD
    # ------------------------------------------------------------------

    def add_stops_to_route(
        self, route_id: int, stop_defs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        from app.Models.dispatch_models import DispatchRoute, DispatchRouteStop

        route = DispatchRoute.query.get(route_id)
        if not route:
            return []

        max_seq = (
            db.session.query(func.max(DispatchRouteStop.sequence))
            .filter_by(route_id=route_id)
            .scalar()
            or 0
        )

        created = []
        for i, stop_def in enumerate(stop_defs):
            stop = DispatchRouteStop(
                route_id=route_id,
                so_id=stop_def["so_id"],
                shipment_num=stop_def.get("shipment_num"),
                sequence=max_seq + i + 1,
                notes=stop_def.get("notes"),
            )
            db.session.add(stop)
            created.append(stop)

        db.session.commit()
        return [s.to_dict() for s in created]

    def reorder_stops(self, route_id: int, ordered_stop_ids: List[int]) -> bool:
        from app.Models.dispatch_models import DispatchRouteStop

        stops = DispatchRouteStop.query.filter_by(route_id=route_id).all()
        stop_map = {s.id: s for s in stops}

        for seq, stop_id in enumerate(ordered_stop_ids, start=1):
            if stop_id in stop_map:
                stop_map[stop_id].sequence = seq

        db.session.commit()
        return True

    def remove_stop(self, route_id: int, stop_id: int) -> bool:
        from app.Models.dispatch_models import DispatchRouteStop

        stop = DispatchRouteStop.query.filter_by(
            id=stop_id, route_id=route_id
        ).first()
        if not stop:
            return False
        db.session.delete(stop)
        db.session.commit()
        return True

    # ------------------------------------------------------------------
    # Driver Roster
    # ------------------------------------------------------------------

    def get_drivers(self, branch: Optional[str] = None) -> List[Dict[str, Any]]:
        from app.Models.dispatch_models import DispatchDriver

        q = DispatchDriver.query.filter_by(is_active=True)
        if branch:
            branches = self._expand_branch(branch)
            q = q.filter(
                db.or_(
                    DispatchDriver.branch_code.in_(branches),
                    DispatchDriver.branch_code.is_(None),
                )
            )
        return [d.to_dict() for d in q.order_by(DispatchDriver.name).all()]

    def create_driver(
        self,
        name: str,
        phone: Optional[str] = None,
        default_truck_id: Optional[str] = None,
        branch_code: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        from app.Models.dispatch_models import DispatchDriver

        driver = DispatchDriver(
            name=name,
            phone=phone,
            default_truck_id=default_truck_id,
            branch_code=branch_code,
            notes=notes,
        )
        db.session.add(driver)
        db.session.commit()
        return driver.to_dict()

    def update_driver(self, driver_id: int, **kwargs) -> Optional[Dict[str, Any]]:
        from app.Models.dispatch_models import DispatchDriver

        driver = DispatchDriver.query.get(driver_id)
        if not driver:
            return None
        allowed = ("name", "phone", "default_truck_id", "branch_code", "is_active", "notes")
        for key, value in kwargs.items():
            if key in allowed:
                setattr(driver, key, value)
        db.session.commit()
        return driver.to_dict()

    def seed_drivers_from_erp(self, branch: Optional[str] = None) -> List[Dict[str, Any]]:
        """Pull distinct driver names from recent shipment headers and create
        roster entries for any not already present."""
        from app.Models.dispatch_models import DispatchDriver
        from app.Models.models import ERPMirrorShipmentHeader

        cutoff = datetime.utcnow() - timedelta(days=90)
        q = (
            db.session.query(ERPMirrorShipmentHeader.driver)
            .filter(
                ERPMirrorShipmentHeader.driver.isnot(None),
                ERPMirrorShipmentHeader.driver != "",
                ERPMirrorShipmentHeader.is_deleted.is_(False),
                ERPMirrorShipmentHeader.synced_at >= cutoff,
            )
            .distinct()
        )
        if branch:
            branches = self._expand_branch(branch)
            q = q.filter(ERPMirrorShipmentHeader.branch_code.in_(branches))

        existing_names = {
            d.name.upper()
            for d in DispatchDriver.query.with_entities(DispatchDriver.name).all()
        }

        created = []
        for (driver_name,) in q.all():
            name = driver_name.strip()
            if not name or name.upper() in existing_names:
                continue
            driver = DispatchDriver(name=name, branch_code=branch)
            db.session.add(driver)
            existing_names.add(name.upper())
            created.append(driver)

        db.session.commit()
        return [d.to_dict() for d in created]

    # ------------------------------------------------------------------
    # Truck Assignments
    # ------------------------------------------------------------------

    def get_truck_assignments(
        self, assignment_date: date, branch: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        from app.Models.dispatch_models import DispatchTruckAssignment

        q = DispatchTruckAssignment.query.filter_by(assignment_date=assignment_date)
        if branch:
            branches = self._expand_branch(branch)
            q = q.filter(DispatchTruckAssignment.branch_code.in_(branches))
        return [a.to_dict() for a in q.order_by(DispatchTruckAssignment.samsara_vehicle_name).all()]

    def upsert_truck_assignment(
        self,
        assignment_date: date,
        samsara_vehicle_id: str,
        samsara_vehicle_name: Optional[str],
        branch_code: str,
        driver_id: Optional[int] = None,
        route_id: Optional[int] = None,
        notes: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        from app.Models.dispatch_models import DispatchTruckAssignment, DispatchRoute

        assignment = DispatchTruckAssignment.query.filter_by(
            assignment_date=assignment_date,
            samsara_vehicle_id=samsara_vehicle_id,
        ).first()

        if assignment:
            assignment.driver_id = driver_id
            assignment.route_id = route_id
            if samsara_vehicle_name:
                assignment.samsara_vehicle_name = samsara_vehicle_name
            if notes is not None:
                assignment.notes = notes
        else:
            assignment = DispatchTruckAssignment(
                assignment_date=assignment_date,
                branch_code=branch_code,
                samsara_vehicle_id=samsara_vehicle_id,
                samsara_vehicle_name=samsara_vehicle_name,
                driver_id=driver_id,
                route_id=route_id,
                notes=notes,
                created_by=user_id,
            )
            db.session.add(assignment)

        # Also update the route's truck_id if a route is assigned
        if route_id:
            route = DispatchRoute.query.get(route_id)
            if route:
                route.truck_id = samsara_vehicle_id

        db.session.commit()
        return assignment.to_dict()

    def copy_previous_assignments(
        self, target_date: date, branch: str, user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Copy the most recent day's truck assignments as a starting point."""
        from app.Models.dispatch_models import DispatchTruckAssignment

        branches = self._expand_branch(branch)

        # Find most recent assignment date before target
        prev_date = (
            db.session.query(func.max(DispatchTruckAssignment.assignment_date))
            .filter(
                DispatchTruckAssignment.assignment_date < target_date,
                DispatchTruckAssignment.branch_code.in_(branches),
            )
            .scalar()
        )
        if not prev_date:
            return []

        prev_assignments = DispatchTruckAssignment.query.filter_by(
            assignment_date=prev_date
        ).filter(DispatchTruckAssignment.branch_code.in_(branches)).all()

        created = []
        for prev in prev_assignments:
            # Skip if already exists for target date
            existing = DispatchTruckAssignment.query.filter_by(
                assignment_date=target_date,
                samsara_vehicle_id=prev.samsara_vehicle_id,
            ).first()
            if existing:
                continue

            new_assignment = DispatchTruckAssignment(
                assignment_date=target_date,
                branch_code=prev.branch_code,
                samsara_vehicle_id=prev.samsara_vehicle_id,
                samsara_vehicle_name=prev.samsara_vehicle_name,
                driver_id=prev.driver_id,
                route_id=None,  # Don't copy route — routes are date-specific
                created_by=user_id,
            )
            db.session.add(new_assignment)
            created.append(new_assignment)

        db.session.commit()
        return [a.to_dict() for a in created]

    # ------------------------------------------------------------------
    # KPIs
    # ------------------------------------------------------------------

    def get_daily_kpis(
        self, kpi_date: date, branch: Optional[str] = None
    ) -> Dict[str, Any]:
        from app.Models.dispatch_models import (
            DispatchRoute,
            DispatchRouteStop,
            DispatchTruckAssignment,
        )
        from app.Models.models import ERPMirrorShipmentHeader, ERPMirrorSalesOrderHeader

        branches = self._expand_branch(branch) if branch else None

        # Route counts
        route_q = DispatchRoute.query.filter_by(route_date=kpi_date)
        if branches:
            route_q = route_q.filter(DispatchRoute.branch_code.in_(branches))
        routes = route_q.all()
        routes_planned = sum(1 for r in routes if r.status in ("planned", "dispatched", "in_progress", "completed"))
        routes_dispatched = sum(1 for r in routes if r.status in ("dispatched", "in_progress"))

        # Stop counts from local route stops
        route_ids = [r.id for r in routes]
        assigned_stop_count = 0
        if route_ids:
            assigned_stop_count = DispatchRouteStop.query.filter(
                DispatchRouteStop.route_id.in_(route_ids)
            ).count()

        # Truck assignments
        truck_q = DispatchTruckAssignment.query.filter_by(assignment_date=kpi_date)
        if branches:
            truck_q = truck_q.filter(DispatchTruckAssignment.branch_code.in_(branches))
        trucks_assigned = truck_q.filter(DispatchTruckAssignment.route_id.isnot(None)).count()

        # ERP shipment counts for today
        ship_q = ERPMirrorShipmentHeader.query.filter(
            ERPMirrorShipmentHeader.is_deleted.is_(False),
        )
        if branches:
            ship_q = ship_q.filter(ERPMirrorShipmentHeader.branch_code.in_(branches))

        # SO counts — open orders expected today
        so_q = ERPMirrorSalesOrderHeader.query.filter(
            ERPMirrorSalesOrderHeader.is_deleted.is_(False),
            ERPMirrorSalesOrderHeader.expect_date >= datetime.combine(kpi_date, datetime.min.time()),
            ERPMirrorSalesOrderHeader.expect_date < datetime.combine(kpi_date + timedelta(days=1), datetime.min.time()),
            ERPMirrorSalesOrderHeader.so_status.notin_(["I", "C", "X", "CAN", "CANCEL"]),
        )
        if branches:
            so_q = so_q.filter(ERPMirrorSalesOrderHeader.branch_code.in_(branches))
        total_stops = so_q.count()

        return {
            "date": kpi_date.isoformat(),
            "total_stops": total_stops,
            "unassigned": max(0, total_stops - assigned_stop_count),
            "routes_planned": routes_planned,
            "routes_dispatched": routes_dispatched,
            "routes_total": len(routes),
            "trucks_out": trucks_assigned,
            "assigned_stops": assigned_stop_count,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _expand_branch(branch: Optional[str]) -> List[str]:
        """Expand a branch string (possibly comma-separated or alias) to a list
        of canonical branch codes."""
        if not branch:
            return []
        raw = [b.strip().upper() for b in branch.split(",") if b.strip()]
        expanded: List[str] = []
        for b in raw:
            if b in ("GRIMES", "GRIMES AREA", "GRIMES_AREA"):
                expanded.extend(["20GR", "25BW"])
            else:
                expanded.append(b)
        return sorted(set(expanded))

    def generate_manifest_pdf(self, items: List[Dict[str, Any]]) -> BytesIO:
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        total = len(items)
        logo_path = os.environ.get("LOGO_PATH") or r"C:\Users\amcgrean\python\dd\beisser_logo_full_color_CMYK (print).png"

        for page_number, item in enumerate(items, start=1):
            self._draw_manifest_page(pdf, item, page_number, total, logo_path)
            pdf.showPage()

        pdf.save()
        buffer.seek(0)
        return buffer

    def _draw_manifest_page(
        self, pdf: canvas.Canvas, item: Dict[str, Any], page_number: int, total_pages: int, logo_path: str
    ) -> None:
        width, height = letter
        margin = 0.6 * inch
        x0 = margin
        y0 = height - margin
        logo_width = 1.8 * inch
        logo_height = 0.7 * inch

        if logo_path and os.path.exists(logo_path):
            try:
                pdf.drawImage(
                    logo_path,
                    x0,
                    y0 - logo_height + 6,
                    width=logo_width,
                    height=logo_height,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                pass
            title_x = x0 + logo_width + 10
        else:
            title_x = x0

        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(title_x, y0, "Dispatch Manifest")
        pdf.setFont("Helvetica", 9)
        pdf.drawRightString(width - margin, y0, datetime.now().strftime("%Y-%m-%d %H:%M"))
        y = y0 - 0.25 * inch
        pdf.line(margin, y, width - margin, y)
        y -= 0.2 * inch

        order_id = str(item.get("id", ""))
        qr_img = qrcode.make(f"SO:{order_id}")
        qr_buf = BytesIO()
        qr_img.save(qr_buf, format="PNG")
        qr_buf.seek(0)
        pdf.drawImage(
            ImageReader(qr_buf),
            width - margin - 1.5 * inch,
            y,
            1.5 * inch,
            1.5 * inch,
            preserveAspectRatio=True,
            mask="auto",
        )

        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(x0, y, f"Order: {order_id}")
        pdf.setFont("Helvetica", 10)
        y -= 0.22 * inch
        pdf.drawString(
            x0,
            y,
            f"Type: {(item.get('doc_kind') or item.get('type') or '').upper()}    Status: {item.get('so_status') or ''}",
        )
        y -= 0.18 * inch
        pdf.drawString(
            x0,
            y,
            f"Branch: {item.get('branch') or ''}    Route: {item.get('route_id') or ''}    Shipment#: {item.get('shipment_num') or ''}",
        )
        y -= 0.18 * inch
        pdf.drawString(
            x0,
            y,
            f"Driver: {item.get('driver') or ''}    Expected: {str(item.get('expected_date') or '')[:10]}",
        )
        y -= 0.28 * inch
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(x0, y, "Ship-To:")
        y -= 0.2 * inch
        pdf.setFont("Helvetica", 10)
        pdf.drawString(x0, y, (item.get("shipto_name") or "")[:80])
        y -= 0.18 * inch
        pdf.drawString(x0, y, (item.get("address") or "")[:110])
        y -= 0.28 * inch

        y = self._draw_lines_table(pdf, x0, y, item.get("lines") or [])
        y -= 0.2 * inch
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(x0, y, "Notes / Instructions:")
        y -= 0.18 * inch
        pdf.setStrokeColor(colors.grey)
        box_top = y
        box_height = 1.6 * inch
        pdf.rect(x0, box_top - box_height, width - 2 * margin, box_height, stroke=1, fill=0)
        for index in range(1, 6):
            line_y = box_top - (index * (box_height / 5))
            pdf.line(x0 + 6, line_y, width - margin - 6, line_y)
        y = box_top - box_height - 0.25 * inch
        pdf.setStrokeColor(colors.black)
        pdf.line(x0, y, x0 + 2.5 * inch, y)
        pdf.drawString(x0, y - 12, "Customer Signature")
        pdf.line(x0 + 3.0 * inch, y, x0 + 5.5 * inch, y)
        pdf.drawString(x0 + 3.0 * inch, y - 12, "Printed Name")
        pdf.drawRightString(width - margin, margin / 2, f"Page {page_number} of {total_pages}")

    def _draw_lines_table(self, pdf: canvas.Canvas, x0: float, y: float, lines: List[Dict[str, Any]], max_rows: int = 12) -> float:
        if not lines:
            return y

        columns = [
            ("line_no", "Ln", 0.4 * inch),
            ("item_id", "Item", 1.2 * inch),
            ("item_description", "Description", 2.4 * inch),
            ("qty_ordered", "Ord", 0.6 * inch),
            ("qty_shipped", "Shp", 0.6 * inch),
            ("uom", "UOM", 0.5 * inch),
            ("weight", "Wt", 0.5 * inch),
        ]

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(x0, y, "Shipment Lines")
        y -= 0.18 * inch
        pdf.setFont("Helvetica", 9)
        x = x0
        for _, title, width in columns:
            pdf.drawString(x, y, title)
            x += width
        y -= 0.16 * inch
        pdf.setStrokeColor(colors.grey)
        pdf.line(x0, y, x0 + sum(width for _, _, width in columns), y)
        y -= 0.08 * inch
        pdf.setStrokeColor(colors.black)

        for line in lines[:max_rows]:
            x = x0
            for key, _, width in columns:
                pdf.drawString(x, y, str(line.get(key, ""))[:28])
                x += width
            y -= 0.16 * inch
            if y < 1.1 * inch:
                break
        return y
