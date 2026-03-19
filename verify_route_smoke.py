import os
import tempfile
from pathlib import Path


def main():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ.pop("CENTRAL_DB_URL", None)

    from app import create_app
    from app.extensions import db
    from app.Models.models import CustomerNote, Pickster
    from app.Routes import sales_routes
    from app.Services.erp_service import ERPService

    app = create_app()
    app.config["TESTING"] = True

    sample_orders = [
        {
            "so_number": "SO100",
            "customer_name": "Acme Lumber",
            "customer_code": "ACME",
            "reference": "REF-1",
            "expect_date": "2026-03-18",
            "so_status": "O",
            "item_number": "ITEM1",
            "description": "Door Slab",
            "count": 2,
        }
    ]
    sample_products = [
        {"item_number": "ITEM1", "description": "Door Slab", "quantity_on_hand": 4}
    ]
    sample_reports = {
        "daily_orders": [{"expect_date": "2026-03-18", "count": 1}],
        "top_customers": [
            {"customer_name": "Acme Lumber", "customer_code": "ACME", "order_count": 1}
        ],
        "status_breakdown": [{"so_status": "O", "count": 1}],
    }
    sample_wos = [
        {
            "wo_id": "WO1",
            "so_number": "SO100",
            "description": "Build door",
            "item_number": "ITEM1",
            "status": "Open",
            "qty": 1,
            "department": "DOOR",
            "customer_name": "Acme Lumber",
            "reference": "REF-1",
        }
    ]
    sample_so_details = [
        {
            "so_number": "SO100",
            "sequence": 1,
            "item_number": "ITEM1",
            "description": "Door Slab",
            "handling_code": "DOOR",
            "qty": 1,
        }
    ]

    def fake_get_sales_hub_metrics(self=None):
        return {"open_orders_count": 1, "total_orders_today": 1}

    def fake_get_sales_rep_metrics(self=None, period_days=30):
        return {"active_customers": 1, "open_orders_value": 0, "monthly_goal_progress": 0}

    def fake_get_sales_order_status(self=None, q="", limit=100):
        return sample_orders

    def fake_get_sales_invoice_lookup(self=None, q="", date_from="", date_to="", limit=50):
        return sample_orders

    def fake_get_sales_customer_orders(self=None, customer_number="", q="", limit=None):
        return sample_orders

    def fake_get_sales_products(self=None, q="", limit=50):
        return sample_products

    def fake_get_sales_reports(self=None, period_days=30):
        return sample_reports

    def fake_get_open_work_orders(self):
        return sample_wos

    def fake_get_work_orders_by_barcode(self, barcode):
        return [{"wo_number": "WO1", "item_number": "ITEM1", "description": "Build door"}]

    def fake_get_historical_so_summary(self, so_numbers=None):
        return [{"so_number": "SO100", "customer_name": "Acme Lumber"}]

    def fake_get_so_header(self, so_number):
        return {
            "so_number": so_number,
            "customer_name": "Acme Lumber",
            "address": "123 Main",
            "reference": "REF-1",
        }

    def fake_get_so_details(self, so_number):
        return sample_so_details

    def fake_get_open_so_summary(self):
        return [
            {
                "so_number": "SO100",
                "customer_name": "Acme Lumber",
                "address": "123 Main",
                "reference": "REF-1",
                "line_count": 1,
                "handling_code": "DOOR",
            }
        ]

    def fake_get_sales_delivery_tracker(self, branch_id=None):
        return []

    sales_routes.erp.get_sales_hub_metrics = fake_get_sales_hub_metrics
    sales_routes.erp.get_sales_rep_metrics = fake_get_sales_rep_metrics
    sales_routes.erp.get_sales_order_status = fake_get_sales_order_status
    sales_routes.erp.get_sales_invoice_lookup = fake_get_sales_invoice_lookup
    sales_routes.erp.get_sales_customer_orders = fake_get_sales_customer_orders
    sales_routes.erp.get_sales_products = fake_get_sales_products
    sales_routes.erp.get_sales_reports = fake_get_sales_reports
    ERPService.get_open_work_orders = fake_get_open_work_orders
    ERPService.get_work_orders_by_barcode = fake_get_work_orders_by_barcode
    ERPService.get_historical_so_summary = fake_get_historical_so_summary
    ERPService.get_so_header = fake_get_so_header
    ERPService.get_so_details = fake_get_so_details
    ERPService.get_open_so_summary = fake_get_open_so_summary
    ERPService.get_sales_delivery_tracker = fake_get_sales_delivery_tracker

    with app.app_context():
        db.drop_all(bind_key=[None])
        db.create_all(bind_key=[None])
        builder = Pickster(name="Builder Bob", user_type="door_builder")
        supervisor = Pickster(name="Supervisor Sue", user_type="picker")
        db.session.add_all([builder, supervisor])
        db.session.add(
            CustomerNote(
                customer_number="Acme",
                note_type="Call",
                body="Initial note",
                rep_name="Rep",
            )
        )
        db.session.commit()

    client = app.test_client()
    checks = [
        ("GET", "/sales/hub", None),
        ("GET", "/sales/order-status?q=acme", None),
        ("GET", "/sales/customer-profile/Acme", None),
        ("GET", "/sales/customer-notes/Acme", None),
        ("POST", "/sales/customer-notes/Acme", {"note_type": "Call", "body": "Follow up", "rep_name": "Rep"}),
        ("GET", "/sales/invoice-lookup?q=SO100", None),
        ("GET", "/sales/products?q=ITEM1", None),
        ("GET", "/sales/reports", None),
        ("GET", "/sales/order-history/Acme?q=SO100", None),
        ("GET", "/work_orders", None),
        ("GET", "/work_orders/open/1", None),
        ("GET", "/work_orders/scan/1", None),
        ("GET", "/work_orders/select?user_id=1&barcode=SO100", None),
        ("POST", "/work_orders/start", {"user_id": "1", "selected_items": ["WO1|ITEM1|Build door"]}),
        ("GET", "/supervisor/dashboard", None),
        ("GET", "/supervisor/work_orders", None),
        (
            "POST",
            "/supervisor/assign_wo",
            {
                "staff_id": "1",
                "selected_wos[]": [
                    '{"wo_id": "WO1", "so_number": "SO100", "item_number": "ITEM1", "description": "Build door"}'
                ],
            },
        ),
    ]

    failures = []
    for method, url, data in checks:
        if method == "GET":
            response = client.get(url, follow_redirects=True)
        else:
            response = client.post(url, data=data, follow_redirects=True)
        print(f"{method} {url} -> {response.status_code}")
        if response.status_code >= 400:
            failures.append((method, url, response.status_code))

    if failures:
        raise SystemExit(f"Route smoke failed: {failures}")

    print("route smoke passed")

    try:
        Path(db_path).unlink(missing_ok=True)
    except PermissionError:
        pass


if __name__ == "__main__":
    main()
