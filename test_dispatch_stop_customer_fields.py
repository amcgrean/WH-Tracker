from datetime import date

from app.Services.dispatch_service import DispatchService
from app.Services.erp_service import ERPService


class FakeCursor:
    def __init__(self, rows, columns):
        self._rows = rows
        self.description = [(column,) for column in columns]

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self._rows

    def close(self):
        return None


class FakeConnection:
    def __init__(self, rows, columns):
        self._cursor = FakeCursor(rows, columns)

    def cursor(self):
        return self._cursor

    def close(self):
        return None


def test_get_dispatch_stops_central_keeps_db_name_and_address_without_gps(monkeypatch):
    service = ERPService()
    service.central_db_mode = True

    def fake_query(sql, params, expanding=None):
        assert "COALESCE(cs.shipto_name, c.cust_name) AS shipto_name" in sql
        return [{
            "id": "1001",
            "doc_kind": "delivery",
            "expected_date": "2026-03-23",
            "lat": None,
            "lon": None,
            "address": None,
            "so_status": "K",
            "so_type": "SO",
            "shipto_name": "Acme Jobsite",
            "shipto_address": "123 Main St Des Moines IA 50309",
            "customer_name": "Acme Lumber",
            "customer_code": "ACME",
            "ship_to_number": "1",
            "shipment_num": 10,
            "route_id": "R1",
            "driver": "Driver A",
            "branch": "20GR",
        }]

    monkeypatch.setattr(service, "_mirror_query", fake_query)
    monkeypatch.setattr(service, "_load_dispatch_gps_map", lambda: {})
    monkeypatch.setattr(service, "_aggregate_dispatch_details", lambda so_ids: {})

    rows = service.get_dispatch_stops(
        start=date(2026, 3, 20),
        end=date(2026, 3, 24),
        include_no_gps=True,
    )

    assert rows[0]["shipto_name"] == "Acme Jobsite"
    assert rows[0]["customer_name"] == "Acme Lumber"
    assert rows[0]["address"] == "123 Main St Des Moines IA 50309"


def test_get_dispatch_stops_central_trims_and_falls_back_when_names_are_blank(monkeypatch):
    service = ERPService()
    service.central_db_mode = True

    def fake_query(sql, params, expanding=None):
        return [{
            "id": "1003",
            "doc_kind": "delivery",
            "expected_date": "2026-03-23",
            "lat": None,
            "lon": None,
            "address": "   ",
            "so_status": "K",
            "so_type": "SO",
            "shipto_name": "   ",
            "shipto_address": "  789 Elm St Des Moines IA 50310  ",
            "customer_name": "   ",
            "customer_code": "ACME",
            "ship_to_number": "3",
            "shipment_num": 12,
            "route_id": "R3",
            "driver": "Driver C",
            "branch": "20GR",
        }]

    monkeypatch.setattr(service, "_mirror_query", fake_query)
    monkeypatch.setattr(service, "_load_dispatch_gps_map", lambda: {})
    monkeypatch.setattr(service, "_aggregate_dispatch_details", lambda so_ids: {})

    rows = service.get_dispatch_stops(
        start=date(2026, 3, 20),
        end=date(2026, 3, 24),
        include_no_gps=True,
    )

    assert rows[0]["customer_name"] == "Unknown Customer"
    assert rows[0]["shipto_name"] == "Unknown Customer"
    assert rows[0]["address"] == "789 Elm St Des Moines IA 50310"


def test_dispatch_service_get_stops_falls_back_to_db_name_and_address_without_gps(monkeypatch):
    rows = [
        (
            1002,
            "delivery",
            "2026-03-23",
            None,
            None,
            None,
            "S",
            "SO",
            None,
            "456 Oak Ave Ames IA 50010",
            "Acme Lumber",
            11,
            "R2",
            "Driver B",
            "25BW",
            "ACME",
            "2",
        )
    ]
    columns = [
        "id",
        "doc_kind",
        "expected_date",
        "lat",
        "lon",
        "address",
        "so_status",
        "so_type",
        "shipto_name",
        "shipto_address",
        "customer_name",
        "shipment_num",
        "route_id",
        "driver",
        "branch",
        "CustomerCode",
        "ShipToNumber",
    ]

    service = DispatchService()
    monkeypatch.setattr(service, "_connect", lambda: FakeConnection(rows, columns))
    monkeypatch.setattr(service, "_load_gps_map", lambda: {})
    monkeypatch.setattr(service, "_aggregate_shipment_details", lambda so_ids: {})

    result = service.get_stops(
        start=date(2026, 3, 20),
        end=date(2026, 3, 24),
        include_no_gps=True,
    )

    assert result[0]["shipto_name"] == "Acme Lumber"
    assert result[0]["customer_name"] == "Acme Lumber"
    assert result[0]["address"] == "456 Oak Ave Ames IA 50010"
    assert "shipto_address" not in result[0]
