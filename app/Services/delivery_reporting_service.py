from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from app.Services.erp_service import ERPService


class DeliveryReportingService:
    """
    Delivery reporting backed by the mirrored cloud ERP database.

    Metric definitions follow the local SQL report rules:
    - Delivered order: distinct store + ship_date + sales order with non-null ship_date.
    - Same-day delivery: order_date == ship_date.
    - Same-day after-noon: same-day delivery and order_time >= 12:00 PM.
    - Sale type groups:
        Delivery, Add On, Transfer -> Delivery
        Credit -> Credit
        WillCall -> Will Call
        Everything else -> raw non-null sale type
    - Reference piece count:
        Use tally piece_count when available.
        Otherwise fall back to shipped qty only for piece-based UOMs.
    """

    STORE_CODES = ("20GR", "25BW", "10FD", "40CV")
    PIECE_BASED_UOMS = {"EA", "EACH", "PC", "PCS"}
    FLAT_BED_SHIP_VIAS = {"FORK NEEDED", "SMALL TRUCK", "DUMP LOAD", "PICKUP TRUCK", "SEMI-NO FORK"}
    VAN_SHIP_VIAS = {"GR_VAN", "VAN"}
    SALE_TYPE_PRIORITY = ("Delivery", "Credit", "Will Call")

    def __init__(self) -> None:
        self.erp = ERPService()

    def get_dashboard_payload(self, sale_type: str = "all", detail_limit: int = 250) -> dict[str, Any]:
        self._require_central_db()
        rows = self._fetch_order_rows()
        available_sale_types = self._available_sale_types(rows)
        filtered_rows = self._filter_sale_type(rows, sale_type)

        today = date.today()
        start_30d = today - timedelta(days=29)
        start_12m = self._month_floor(self._shift_months(today, -11))

        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "stores": list(self.STORE_CODES),
            "sale_type_filter": self._normalize_sale_type_filter(sale_type),
            "available_sale_types": available_sale_types,
            "metric_definitions": {
                "delivered_orders": "Distinct delivered orders using ship_date as the delivery date.",
                "same_day_delivery_pct": "Same-day delivered orders divided by delivered orders.",
                "after_noon_share_of_same_day_deliveries": "Same-day-after-noon orders divided by same-day delivered orders.",
                "reference_piece_count": "Tally piece_count when available, otherwise shipped qty only for piece-based UOMs.",
            },
            "windows": {
                "30d": self._build_window_payload(filtered_rows, start_30d, detail_limit),
                "12m": self._build_window_payload(filtered_rows, start_12m, detail_limit),
            },
            "trends": {
                "daily_30d": self._build_daily_trend(filtered_rows, start_30d, today),
                "monthly_12m": self._build_monthly_trend(filtered_rows, start_12m, today),
            },
        }

    def get_export_rows(self, sale_type: str = "all", window: str = "30d") -> list[dict[str, Any]]:
        self._require_central_db()
        rows = self._filter_sale_type(self._fetch_order_rows(), sale_type)
        start_date = self._window_start(window)
        return [
            self._serialize_detail_row(row)
            for row in sorted(
                (row for row in rows if row["ship_date"] >= start_date),
                key=lambda item: (item["ship_date"], item["store"], item["so_id"]),
                reverse=True,
            )
        ]

    def _require_central_db(self) -> None:
        if not self.erp.central_db_mode:
            raise RuntimeError("Delivery reporting requires CENTRAL_DB_URL / DATABASE_URL mirror access.")

    def _safe_columns(self, table_name: str) -> set[str]:
        try:
            return set(self.erp._mirror_columns(table_name))
        except Exception:
            return set()

    def _month_floor(self, value: date) -> date:
        return value.replace(day=1)

    def _shift_months(self, value: date, offset: int) -> date:
        month_index = (value.year * 12 + value.month - 1) + offset
        year = month_index // 12
        month = month_index % 12 + 1
        return date(year, month, 1)

    def _window_start(self, window: str) -> date:
        normalized = (window or "30d").strip().lower()
        today = date.today()
        if normalized == "12m":
            return self._month_floor(self._shift_months(today, -11))
        return today - timedelta(days=29)

    def _fetch_order_rows(self) -> list[dict[str, Any]]:
        so_columns = self._safe_columns("erp_mirror_so_header")
        ship_columns = self._safe_columns("erp_mirror_shipments_header")
        ship_detail_columns = self._safe_columns("erp_mirror_shipments_detail")
        item_columns = self._safe_columns("erp_mirror_item")
        tally_columns = self._safe_columns("erp_mirror_shipments_tally_detail")

        order_time_expr = "CAST(NULL AS TEXT)"
        for candidate in ("order_time", "created_time"):
            if candidate in so_columns:
                order_time_expr = f"CAST(soh.{candidate} AS TEXT)"
                break

        ship_via_expr = "soh.ship_via"
        if "ship_via" in ship_columns:
            ship_via_expr = "COALESCE(sh.ship_via, soh.ship_via)"

        line_no_expr = "sd.line_no" if "line_no" in ship_detail_columns else "sd.id"

        qty_candidates = [name for name in ("qty_shipped", "qty", "qty_ordered") if name in ship_detail_columns]
        qty_expr = "COALESCE(" + ", ".join(f"sd.{name}" for name in qty_candidates) + ", 0)" if qty_candidates else "0"

        uom_candidates = []
        for name in ("uom", "uom_ptr", "shipped_uom", "qty_uom", "qty_uom_ptr", "price_uom_ptr"):
            if name in ship_detail_columns:
                uom_candidates.append(f"CAST(sd.{name} AS TEXT)")
        if "stocking_uom" in item_columns:
            uom_candidates.append("CAST(i.stocking_uom AS TEXT)")
        uom_expr = "COALESCE(" + ", ".join(uom_candidates) + ", '')" if uom_candidates else "''"

        tally_cte = ""
        tally_join = ""
        piece_expr = "CAST(NULL AS NUMERIC)"
        required_tally_columns = {"system_id", "so_id", "shipment_num", "piece_count"}
        if required_tally_columns.issubset(tally_columns):
            sequence_column = "sequence" if "sequence" in tally_columns else ("line_no" if "line_no" in tally_columns else None)
            item_ptr_column = "item_ptr" if "item_ptr" in tally_columns else None
            join_parts = [
                "tally.system_id = sh.system_id",
                "CAST(tally.so_id AS TEXT) = CAST(sh.so_id AS TEXT)",
                "CAST(tally.shipment_num AS TEXT) = CAST(sh.shipment_num AS TEXT)",
            ]
            group_parts = ["system_id", "so_id", "shipment_num"]
            select_parts = [
                "system_id",
                "so_id",
                "shipment_num",
                "SUM(COALESCE(piece_count, 0)) AS piece_count",
            ]
            if sequence_column:
                join_parts.append(f"CAST(tally.{sequence_column} AS TEXT) = CAST({line_no_expr} AS TEXT)")
                group_parts.append(sequence_column)
                select_parts.insert(3, sequence_column)
            if item_ptr_column:
                join_parts.append("CAST(tally.item_ptr AS TEXT) = CAST(sd.item_ptr AS TEXT)")
                group_parts.append(item_ptr_column)
                select_parts.insert(4 if sequence_column else 3, item_ptr_column)

            tally_cte = f"""
                tally AS (
                    SELECT
                        {", ".join(select_parts)}
                    FROM erp_mirror_shipments_tally_detail
                    WHERE is_deleted = false
                    GROUP BY {", ".join(group_parts)}
                ),
            """
            tally_join = f"LEFT JOIN tally ON {' AND '.join(join_parts)}"
            piece_expr = "tally.piece_count"

        start_12m = self._window_start("12m")
        rows = self.erp._mirror_query(
            f"""
            WITH
            {tally_cte}
            shipment_lines AS (
                SELECT
                    sh.system_id AS store,
                    CAST(sh.ship_date AS DATE) AS ship_date,
                    CAST(sh.so_id AS TEXT) AS so_id,
                    COALESCE(NULLIF(TRIM(CAST(soh.sale_type AS TEXT)), ''), 'Unknown') AS sale_type_raw,
                    COALESCE(NULLIF(TRIM(CAST({ship_via_expr} AS TEXT)), ''), 'Unknown') AS ship_via_raw,
                    CAST(soh.created_date AS DATE) AS order_date,
                    {order_time_expr} AS order_time_raw,
                    CAST(sd.item_ptr AS TEXT) AS item_ptr,
                    CONCAT(COALESCE(CAST(sh.shipment_num AS TEXT), ''), ':', COALESCE(CAST({line_no_expr} AS TEXT), '')) AS shipment_line_key,
                    COALESCE({qty_expr}, 0) AS shipped_qty,
                    CASE
                        WHEN {piece_expr} IS NOT NULL THEN COALESCE({piece_expr}, 0)
                        WHEN UPPER(COALESCE({uom_expr}, '')) IN :piece_uoms THEN COALESCE({qty_expr}, 0)
                        ELSE 0
                    END AS reference_piece_count
                FROM erp_mirror_shipments_header sh
                JOIN erp_mirror_shipments_detail sd
                    ON sd.is_deleted = false
                   AND sd.system_id = sh.system_id
                   AND CAST(sd.so_id AS TEXT) = CAST(sh.so_id AS TEXT)
                   AND CAST(sd.shipment_num AS TEXT) = CAST(sh.shipment_num AS TEXT)
                JOIN erp_mirror_so_header soh
                    ON soh.is_deleted = false
                   AND soh.system_id = sh.system_id
                   AND CAST(soh.so_id AS TEXT) = CAST(sh.so_id AS TEXT)
                LEFT JOIN erp_mirror_item i
                    ON i.is_deleted = false
                   AND CAST(i.item_ptr AS TEXT) = CAST(sd.item_ptr AS TEXT)
                {tally_join}
                WHERE sh.is_deleted = false
                  AND CAST(sh.ship_date AS DATE) >= :start_12m
                  AND sh.system_id IN :stores
                  AND UPPER(COALESCE(soh.sale_type, '')) <> 'DIRECT'
            )
            SELECT
                store,
                ship_date,
                so_id,
                sale_type_raw,
                ship_via_raw,
                order_date,
                order_time_raw,
                COUNT(DISTINCT shipment_line_key) AS shipped_line_count,
                COUNT(DISTINCT item_ptr) AS unique_item_count,
                SUM(shipped_qty) AS total_shipped_qty,
                SUM(reference_piece_count) AS reference_piece_count
            FROM shipment_lines
            GROUP BY
                store,
                ship_date,
                so_id,
                sale_type_raw,
                ship_via_raw,
                order_date,
                order_time_raw
            ORDER BY ship_date DESC, store, so_id
            """,
            {
                "start_12m": start_12m.isoformat(),
                "stores": list(self.STORE_CODES),
                "piece_uoms": sorted(self.PIECE_BASED_UOMS),
            },
            expanding={"stores", "piece_uoms"},
        )

        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            store = (row.get("store") or "").strip()
            ship_date = self._coerce_date(row.get("ship_date"))
            order_date = self._coerce_date(row.get("order_date"))
            order_time = self._parse_time_value(row.get("order_time_raw"))
            sale_type_raw = self._clean_text(row.get("sale_type_raw"), default="Unknown")
            sale_type_group = self._normalize_sale_type_group(sale_type_raw)
            ship_via_raw = self._clean_text(row.get("ship_via_raw"), default="Unknown")
            same_day_flag = bool(order_date and ship_date and order_date == ship_date)
            same_day_after_noon_flag = bool(same_day_flag and order_time and order_time >= time(12, 0))

            normalized_rows.append({
                "store": store,
                "ship_date": ship_date,
                "so_id": self._clean_text(row.get("so_id")),
                "sale_type": sale_type_raw,
                "sale_type_group": sale_type_group,
                "ship_via": ship_via_raw,
                "ship_via_bucket": self._bucket_ship_via(store, sale_type_raw, sale_type_group, ship_via_raw),
                "order_date": order_date,
                "order_time": order_time,
                "same_day_flag": same_day_flag,
                "same_day_after_noon_flag": same_day_after_noon_flag,
                "shipped_line_count": int(row.get("shipped_line_count") or 0),
                "unique_item_count": int(row.get("unique_item_count") or 0),
                "total_shipped_qty": self._to_float(row.get("total_shipped_qty")),
                "reference_piece_count": self._to_float(row.get("reference_piece_count")),
            })

        return normalized_rows

    def _coerce_date(self, value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        text = str(value).strip()
        if not text:
            return None
        return datetime.fromisoformat(text[:10]).date()

    def _parse_time_value(self, value: Any) -> time | None:
        if value is None:
            return None
        if isinstance(value, time):
            return value
        text = str(value).strip()
        if not text:
            return None

        normalized = text.replace(".", ":").upper()
        for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p", "%I %p", "%I%p"):
            try:
                return datetime.strptime(normalized, fmt).time()
            except ValueError:
                continue
        return None

    def _clean_text(self, value: Any, default: str = "") -> str:
        text = str(value or "").strip()
        return text or default

    def _to_float(self, value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, Decimal):
            return float(value)
        return float(value or 0)

    def _normalize_sale_type_group(self, sale_type: str) -> str:
        compact = self._clean_text(sale_type, default="Unknown").upper().replace(" ", "")
        if compact in {"DELIVERY", "ADDON", "TRANSFER"}:
            return "Delivery"
        if compact == "CREDIT":
            return "Credit"
        if compact == "WILLCALL":
            return "Will Call"
        return self._clean_text(sale_type, default="Unknown")

    def _bucket_ship_via(self, store: str, sale_type: str, sale_type_group: str, ship_via: str) -> str:
        ship_via_clean = self._clean_text(ship_via, default="Unknown")
        ship_via_upper = ship_via_clean.upper()
        sale_type_upper = self._clean_text(sale_type, default="Unknown").upper().replace(" ", "")

        if sale_type_group == "Will Call" and ship_via_upper == "WILL CALL":
            return f"{store}-WC"
        if sale_type_upper == "TRANSFER":
            return "Transfer"
        if ship_via_upper in self.FLAT_BED_SHIP_VIAS:
            return "Flat Bed"
        if ship_via_upper in self.VAN_SHIP_VIAS:
            return "Van"
        if ship_via_upper == "WILL CALL":
            return "Will Call"
        return ship_via_clean

    def _available_sale_types(self, rows: list[dict[str, Any]]) -> list[str]:
        groups = {row["sale_type_group"] for row in rows if row.get("sale_type_group")}
        ordered = [label for label in self.SALE_TYPE_PRIORITY if label in groups]
        ordered.extend(sorted(group for group in groups if group not in self.SALE_TYPE_PRIORITY))
        return ["All"] + ordered

    def _normalize_sale_type_filter(self, sale_type: str) -> str:
        cleaned = self._clean_text(sale_type, default="All")
        return "All" if cleaned.lower() == "all" else cleaned

    def _filter_sale_type(self, rows: list[dict[str, Any]], sale_type: str) -> list[dict[str, Any]]:
        normalized = self._normalize_sale_type_filter(sale_type)
        if normalized == "All":
            return rows
        return [row for row in rows if row["sale_type_group"].lower() == normalized.lower()]

    def _build_window_payload(self, rows: list[dict[str, Any]], start_date: date, detail_limit: int) -> dict[str, Any]:
        window_rows = [row for row in rows if row["ship_date"] and row["ship_date"] >= start_date]
        sorted_rows = sorted(window_rows, key=lambda item: (item["ship_date"], item["store"], item["so_id"]), reverse=True)
        return {
            "summary": self._metric_block(window_rows),
            "store_comparison": self._store_comparison(window_rows),
            "sale_type_totals": self._group_metrics(window_rows, ("sale_type_group",)),
            "sale_type_totals_by_store": self._group_metrics(window_rows, ("store", "sale_type_group")),
            "sale_type_ship_via_totals": self._group_metrics(window_rows, ("sale_type_group", "ship_via_bucket")),
            "sale_type_ship_via_totals_by_store": self._group_metrics(window_rows, ("store", "sale_type_group", "ship_via_bucket")),
            "detail_total_count": len(sorted_rows),
            "details": [self._serialize_detail_row(row) for row in sorted_rows[: max(1, min(detail_limit, 1000))]],
        }

    def _metric_block(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        delivered_orders = len(rows)
        same_day_delivered_orders = sum(1 for row in rows if row["same_day_flag"])
        same_day_after_noon_count = sum(1 for row in rows if row["same_day_after_noon_flag"])
        total_shipped_qty = sum(row["total_shipped_qty"] for row in rows)
        reference_piece_count = sum(row["reference_piece_count"] for row in rows)

        return {
            "delivered_orders": delivered_orders,
            "same_day_delivered_orders": same_day_delivered_orders,
            "same_day_delivery_pct": self._pct(same_day_delivered_orders, delivered_orders),
            "same_day_after_noon_count": same_day_after_noon_count,
            "after_noon_share_of_same_day_deliveries": self._pct(same_day_after_noon_count, same_day_delivered_orders),
            "total_shipped_qty": round(total_shipped_qty, 2),
            "reference_piece_count": round(reference_piece_count, 2),
        }

    def _store_comparison(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        comparison: list[dict[str, Any]] = []
        for store in self.STORE_CODES:
            store_rows = [row for row in rows if row["store"] == store]
            metrics = self._metric_block(store_rows)
            metrics["store"] = store
            comparison.append(metrics)

        total_metrics = self._metric_block(rows)
        total_metrics["store"] = "Combined"
        comparison.append(total_metrics)
        return comparison

    def _group_metrics(self, rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
        grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[tuple(row[key] for key in keys)].append(row)

        results: list[dict[str, Any]] = []
        for key_values, group_rows in grouped.items():
            payload = {key: value for key, value in zip(keys, key_values)}
            payload.update(self._metric_block(group_rows))
            results.append(payload)

        return sorted(results, key=lambda item: tuple(str(item[key]) for key in keys))

    def _build_daily_trend(self, rows: list[dict[str, Any]], start_date: date, end_date: date) -> list[dict[str, Any]]:
        metrics_by_store_day: dict[tuple[str, date], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if row["ship_date"] and start_date <= row["ship_date"] <= end_date:
                metrics_by_store_day[(row["store"], row["ship_date"])].append(row)

        trend_rows: list[dict[str, Any]] = []
        cursor = start_date
        while cursor <= end_date:
            for store in self.STORE_CODES:
                metrics = self._metric_block(metrics_by_store_day.get((store, cursor), []))
                trend_rows.append({
                    "date": cursor.isoformat(),
                    "store": store,
                    **metrics,
                })
            cursor += timedelta(days=1)
        return trend_rows

    def _build_monthly_trend(self, rows: list[dict[str, Any]], start_date: date, end_date: date) -> list[dict[str, Any]]:
        metrics_by_store_month: dict[tuple[str, date], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            ship_date = row["ship_date"]
            if ship_date and ship_date >= start_date:
                month_key = ship_date.replace(day=1)
                metrics_by_store_month[(row["store"], month_key)].append(row)

        trend_rows: list[dict[str, Any]] = []
        current_month = self._month_floor(start_date)
        final_month = self._month_floor(end_date)
        while current_month <= final_month:
            for store in self.STORE_CODES:
                metrics = self._metric_block(metrics_by_store_month.get((store, current_month), []))
                trend_rows.append({
                    "month": current_month.strftime("%Y-%m"),
                    "label": current_month.strftime("%b %Y"),
                    "store": store,
                    **metrics,
                })
            current_month = self._shift_months(current_month, 1)
        return trend_rows

    def _serialize_detail_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "store": row["store"],
            "ship_date": row["ship_date"].isoformat() if row["ship_date"] else "",
            "so_id": row["so_id"],
            "sale_type": row["sale_type"],
            "sale_type_group": row["sale_type_group"],
            "ship_via": row["ship_via"],
            "ship_via_bucket": row["ship_via_bucket"],
            "order_date": row["order_date"].isoformat() if row["order_date"] else "",
            "order_time": row["order_time"].strftime("%H:%M:%S") if row["order_time"] else "",
            "same_day_flag": row["same_day_flag"],
            "same_day_after_noon_flag": row["same_day_after_noon_flag"],
            "shipped_line_count": row["shipped_line_count"],
            "unique_item_count": row["unique_item_count"],
            "total_shipped_qty": round(row["total_shipped_qty"], 2),
            "reference_piece_count": round(row["reference_piece_count"], 2),
        }

    def _pct(self, numerator: int | float, denominator: int | float) -> float:
        if not denominator:
            return 0.0
        return round((float(numerator) / float(denominator)) * 100, 1)
