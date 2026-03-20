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
