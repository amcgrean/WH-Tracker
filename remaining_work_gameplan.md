# WH-Tracker Project: Status & Remaining Work Gameplan

This document summarizes the current state of the WH-Tracker project based on recent development cycles and identifies the "missing pieces" required to reach full production readiness.

## 1. ERP Synchronization (Critical)
The sync system is the backbone of the application. The Pi sync worker mirrors ERP data into normalized `erp_mirror_*` tables in Supabase.

*   **Status**: Pi sync worker runs continuously with 5-second polling for operational tables. All queries now read from `erp_mirror_*` tables with `is_deleted = false` filtering.
*   **Completed**: Legacy flat tables (`customers`, `sales_orders`, `sales_order_lines`, `inventory`, `dispatch_orders`) and cache tables (`erp_mirror_picks`, `erp_mirror_work_orders`, `erp_delivery_kpis`) have been fully retired.
*   **Missing - Robust Scheduled Sync**: A formal Windows Service or Task Scheduler job is needed for 24/7 reliability on-prem.

## 2. Work Order Tracker (New Module)
The Work Order Tracker is intended to sit alongside the Pick Tracker for specialized millwork/door building flows.

*   **Status**: UI mockups exist ([workcenter.html](file:///c:/Users/amcgrean/python/tracker/workcenter.html), [work order mockup.html](file:///c:/Users/amcgrean/python/tracker/work%20order%20mockup.html)). Backend service [get_open_work_orders](file:///c:/Users/amcgrean/python/tracker/app/Services/erp_service.py#740-819) is implemented in [erp_service.py](file:///c:/Users/amcgrean/python/tracker/app/Services/erp_service.py).
*   **Missing - Assignment Logic**: The "Door Builder" workflow ([routes.py L788-800](file:///c:/Users/amcgrean/python/tracker/app/Routes/routes.py#L788-L800)) needs to be fully wired to the database.
*   **Missing - Real-time Scanning**: Integration with barcode scanning for Work Orders (distinct from Sales Orders) needs validation against Agility SQL schemas.

## 3. Sales Hub Intelligence
A massive suite of 11 customer intelligence features was recently scaffolded.

*   **Status**: Routes and templates for Hub, Rep Dashboard, Customer Profile, Notes, Invoice Lookup, and Reports are present ([sales_routes.py](file:///c:/Users/amcgrean/python/tracker/app/Routes/sales_routes.py)).
*   **Missing - Data Enrichment**: Several routes currently use "proxy" data (e.g., the Product Catalog uses active Picks as a proxy for stock). We need a dedicated product/item sync.
*   **Missing - KPI Accuracy**: Metrics like "Monthly Goal Progress" are currently hardcoded or mocked.

## 4. GPS & Delivery Visualization
Groundwork for GPS tracking is complete, but the visual "Payoff" is still being refined.

*   **Status**: Geocoding logic is active in the sync ([sync_erp.py L128-144](file:///c:/Users/amcgrean/python/tracker/sync_erp.py#L128-L144)). GPS coordinates are being stored for Sales Orders.
*   **Missing - Delivery Board Integration**: The [delivery_tracker.html](file:///c:/Users/amcgrean/python/tracker/app/templates/sales/delivery_tracker.html) needs to be verified for live coordinate plotting (Map view).

## Action Item Gameplan

| Item | Priority | Reference |
| :--- | :--- | :--- |
| **Implement `run_erp_sync.ps1`** | High | [Architectural Pattern](file:///c:/Users/amcgrean/python/tracker/erp_sync_architectural_pattern.md) |
| **Formalize Task Scheduler Job** | High | [Setup Docs](file:///c:/Users/amcgrean/python/tracker/docs/SETUP_LOCAL_SYNC.md) |
| **Finish Work Order Backend** | Medium | [Work Order Needs](file:///c:/Users/amcgrean/python/tracker/summary%20of%20work%20order%20tracking%20needs.txt) |
| **Live Product Catalog Sync** | Medium | [Sales Routes (Products)](file:///c:/Users/amcgrean/python/tracker/app/Routes/sales_routes.py#L153) |
| **Verify GPS Map View** | Medium | [Delivery Board Requirements](file:///c:/Users/amcgrean/python/tracker/docs/DELIVERY_BOARD_DATA_REQUIREMENTS.md) |

---
**Note**: The "AI Ready" SKU list import from previous sessions also needs a final verification to ensure all 4,000+ items are correctly matched during the sync process.
