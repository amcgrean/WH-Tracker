from app.Services.erp_service import ERPService
from app.Routes.sales_routes import _normalize_order_row


def test_get_sales_order_status_central_populates_address_and_extra_fields(monkeypatch):
    service = ERPService()
    service.central_db_mode = True

    def fake_query(sql, params):
        assert "erp_mirror_cust_shipto" in sql
        return [{
            "so_number": "1001",
            "customer_name": "Acme Lumber",
            "customer_code": "ACME",
            "address_1": "123 Main St",
            "city": "Des Moines",
            "expect_date": "2026-03-20",
            "reference": "PO-7",
            "so_status": "O",
            "synced_at": None,
            "handling_code": "DEL",
            "sale_type": "Stock",
            "ship_via": "Truck",
            "line_count": 2,
        }]

    monkeypatch.setattr(service, "_mirror_query", fake_query)

    rows = service.get_sales_order_status(q="Acme", limit=5)

    assert rows == [{
        "so_number": "1001",
        "customer_name": "Acme Lumber",
        "customer_code": "ACME",
        "address_1": "123 Main St",
        "city": "Des Moines",
        "expect_date": "2026-03-20",
        "reference": "PO-7",
        "so_status": "O",
        "synced_at": None,
        "handling_code": "DEL",
        "sale_type": "Stock",
        "ship_via": "Truck",
        "line_count": 2,
        "address": "123 Main St, Des Moines",
    }]


def test_get_sales_customer_orders_central_populates_address_and_extra_fields(monkeypatch):
    service = ERPService()
    service.central_db_mode = True

    def fake_query(sql, params):
        assert "erp_mirror_cust_shipto" in sql
        return [{
            "so_number": "1002",
            "customer_name": "Acme Lumber",
            "customer_code": "ACME",
            "address_1": "456 Oak Ave",
            "city": "Ames",
            "expect_date": "2026-03-21",
            "reference": "PO-8",
            "so_status": "O",
            "synced_at": None,
            "handling_code": "WILLCALL",
            "sale_type": "Stock",
            "ship_via": "Pickup",
            "line_count": 4,
        }]

    monkeypatch.setattr(service, "_mirror_query", fake_query)

    rows = service.get_sales_customer_orders(customer_number="ACME", limit=5)

    assert rows[0]["address"] == "456 Oak Ave, Ames"
    assert rows[0]["handling_code"] == "WILLCALL"
    assert rows[0]["ship_via"] == "Pickup"
    assert rows[0]["line_count"] == 4


def test_normalize_order_row_keeps_address_and_metadata():
    row = _normalize_order_row({
        "so_number": "1003",
        "customer_name": "Acme Lumber",
        "customer_code": "ACME",
        "address": "789 Pine Rd, Boone",
        "expect_date": "2026-03-22",
        "reference": "PO-9",
        "so_status": "O",
        "handling_code": "DEL",
        "sale_type": "Stock",
        "ship_via": "Truck",
        "line_count": 3,
        "synced_at": None,
    })

    assert row["customer_name"] == "Acme Lumber"
    assert row["address"] == "789 Pine Rd, Boone"
    assert row["sale_type"] == "Stock"
    assert row["ship_via"] == "Truck"
    assert row["line_count"] == 3


class _LegacyDeliveryCursor:
    def __init__(self):
        self.params = None

    def execute(self, sql, params):
        self.params = params

    def fetchall(self):
        class Row:
            so_id = "2001"
            cust_name = "Legacy Customer"
            address_1 = "999 Legacy Ln"
            city = "Des Moines"
            reference = "PO-LEG"
            so_status = "S"
            shipment_status = "D"
            invoice_date = None
            system_id = "20GR"
            expect_date = "2026-03-20"
            sale_type = "Stock"
            route = "R3"
            ship_via = "Truck"
            driver = "Legacy Driver"
            status_flag_delivery = "D"

        return [Row()]

    def close(self):
        return None


class _LegacyDeliveryConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        return None


def test_sales_delivery_tracker_legacy_uses_computed_status_label(monkeypatch):
    service = ERPService()
    service.central_db_mode = False
    service.allow_legacy_erp_fallback = True

    cursor = _LegacyDeliveryCursor()
    monkeypatch.setattr(service, "get_connection", lambda: _LegacyDeliveryConnection(cursor))
    monkeypatch.setattr(service, "_get_local_pick_states", lambda _: {})

    rows = service.get_sales_delivery_tracker()

    assert rows[0]["status_label"] == "STAGED - DELIVERED"
    assert len(cursor.params) == 5


def test_require_central_db_allows_explicit_legacy_fallback():
    service = ERPService()
    service.central_db_mode = False
    service.allow_legacy_erp_fallback = True

    # Should not raise when legacy fallback is explicitly enabled.
    service._require_central_db_for_cloud_mode()
