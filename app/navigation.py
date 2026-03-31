from __future__ import annotations

from copy import deepcopy
from typing import Iterable

from flask import current_app, request, session, url_for


# ---------------------------------------------------------------------------
# Navigation Sections
# ---------------------------------------------------------------------------
# Roles: "*" = everyone. Add more specific roles to restrict access.
# coming_soon=True   → section renders with a placeholder (no items required).
# ---------------------------------------------------------------------------

NAV_SECTIONS = [
    # ------------------------------------------------------------------
    # DISPATCH
    # ------------------------------------------------------------------
    {
        "id": "dispatch",
        "label": "Dispatch",
        "icon": "fas fa-route",
        "roles": ["delivery", "dispatch", "sales", "ops", "manager"],
        "items": [
            {
                "id": "dispatch_console",
                "label": "Dispatch Console",
                "endpoint": "dispatch.index",
                "icon": "fas fa-route",
                "description": "Coordinate routes, stops, and live dispatch operations.",
                "roles": ["dispatch", "delivery", "ops"],
                "permissions": ["dispatch.view"],
            },
            {
                "id": "delivery_tracker",
                "label": "Delivery Tracker",
                "endpoint": "main.sales_delivery_tracker",
                "icon": "fas fa-shipping-fast",
                "description": "Track scheduled deliveries and branch status.",
                "roles": ["delivery", "dispatch", "sales", "ops"],
                "permissions": ["delivery.view"],
            },
            {
                "id": "delivery_reporting",
                "label": "Delivery Reporting",
                "endpoint": "main.operations_delivery_reporting",
                "icon": "fas fa-chart-bar",
                "description": "Manager dashboard for same-day delivery performance.",
                "roles": ["ops", "manager"],
                "permissions": ["delivery.reporting"],
            },
            {
                "id": "fleet_map",
                "label": "Fleet Map",
                "endpoint": "main.delivery_map",
                "icon": "fas fa-map-marked-alt",
                "description": "Live fleet GPS board.",
                "roles": ["delivery", "dispatch", "sales", "ops"],
                "permissions": ["delivery.map"],
            },
            {
                "id": "credits",
                "label": "RMA Credits",
                "endpoint": "main.credits_search",
                "icon": "fas fa-file-image",
                "description": "Search and review credit and RMA image uploads.",
                "roles": ["credits", "delivery", "sales", "ops"],
                "permissions": ["credits.view"],
            },
        ],
    },
    # ------------------------------------------------------------------
    # SALES
    # ------------------------------------------------------------------
    {
        "id": "sales",
        "label": "Sales",
        "icon": "fas fa-handshake",
        "roles": ["sales", "ops"],
        "items": [
            {
                "id": "sales_hub",
                "label": "Sales Hub",
                "endpoint": "sales.hub",
                "icon": "fas fa-th",
                "description": "Personalized dashboard and workspace launcher.",
                "roles": ["sales", "ops"],
                "permissions": ["sales.view"],
            },
            {
                "id": "transactions",
                "label": "Sales Transactions",
                "endpoint": "sales.transactions",
                "icon": "fas fa-exchange-alt",
                "description": "Search and act on active orders across all statuses.",
                "roles": ["sales", "ops", "delivery"],
                "permissions": ["sales.orders"],
            },
            {
                "id": "purchase_history",
                "label": "Purchase History",
                "endpoint": "sales.history",
                "icon": "fas fa-history",
                "description": "Research past purchases, pricing, and order patterns.",
                "roles": ["sales", "ops"],
                "permissions": ["sales.history"],
            },
            {
                "id": "products",
                "label": "Products & Stock",
                "endpoint": "sales.products",
                "icon": "fas fa-boxes",
                "description": "Browse products and check stock levels.",
                "roles": ["sales", "ops"],
                "permissions": ["sales.products"],
            },
            {
                "id": "reports",
                "label": "Reports & Analytics",
                "endpoint": "sales.reports",
                "icon": "fas fa-chart-area",
                "description": "Sales analytics, trends, and performance reports.",
                "roles": ["sales", "ops"],
                "permissions": ["sales.reports"],
            },
        ],
    },
    # ------------------------------------------------------------------
    # INVENTORY  (warehouse operations + picking workflows)
    # ------------------------------------------------------------------
    {
        "id": "inventory",
        "label": "Inventory",
        "icon": "fas fa-boxes",
        "roles": ["ops", "warehouse", "supervisor", "production"],
        "items": [
            {
                "id": "pick_tracker",
                "label": "Pick Tracker",
                "endpoint": "main.index",
                "icon": "fas fa-barcode",
                "description": "Launch picker workflows and barcode entry.",
                "roles": ["ops", "warehouse", "supervisor"],
                "permissions": ["pick.view"],
            },
            {
                "id": "open_picks",
                "label": "Open Picks",
                "endpoint": "main.pickers_picks",
                "icon": "fas fa-clipboard-list",
                "description": "Monitor live open picks and throughput.",
                "roles": ["ops", "warehouse", "supervisor"],
                "permissions": ["pick.monitor"],
            },
            {
                "id": "historical_stats",
                "label": "Historical Stats",
                "endpoint": "main.picker_stats",
                "icon": "fas fa-chart-line",
                "description": "Review completed picking performance.",
                "roles": ["ops", "warehouse", "supervisor"],
                "permissions": ["pick.analytics"],
            },
            {
                "id": "warehouse_hub",
                "label": "Warehouse Hub",
                "endpoint": "main.warehouse_select",
                "icon": "fas fa-warehouse",
                "description": "Choose handling views before drilling into the floor boards.",
                "roles": ["warehouse", "ops", "supervisor"],
                "permissions": ["warehouse.view"],
            },
            {
                "id": "warehouse_grouping",
                "label": "Dept Grouping",
                "endpoint": "main.warehouse_board",
                "icon": "fas fa-stream",
                "description": "See open work grouped by department or handling code.",
                "roles": ["warehouse", "ops", "supervisor"],
                "permissions": ["warehouse.board"],
            },
            {
                "id": "warehouse_orders",
                "label": "Full Order View",
                "endpoint": "main.board_orders",
                "icon": "fas fa-layer-group",
                "description": "View complete sales orders with assignment context.",
                "roles": ["warehouse", "ops", "supervisor"],
                "permissions": ["warehouse.orders"],
            },
            {
                "id": "work_orders",
                "label": "Work Order Tracker",
                "endpoint": "main.work_orders",
                "icon": "fas fa-hammer",
                "description": "Start and complete production work orders.",
                "roles": ["production", "ops", "supervisor"],
                "permissions": ["work_orders.view"],
            },
            {
                "id": "supervisor_dashboard",
                "label": "Supervisor Dashboard",
                "endpoint": "main.supervisor_dashboard",
                "icon": "fas fa-user-shield",
                "description": "See live team status and current assignments.",
                "roles": ["supervisor", "ops", "warehouse"],
                "permissions": ["supervisor.dashboard"],
            },
            {
                "id": "work_order_board",
                "label": "Work Order Board",
                "endpoint": "main.supervisor_work_orders",
                "icon": "fas fa-tasks",
                "description": "Assign production jobs from a supervisor board.",
                "roles": ["supervisor", "production", "ops"],
                "permissions": ["supervisor.work_orders"],
            },
        ],
    },
    # ------------------------------------------------------------------
    # PURCHASING
    # ------------------------------------------------------------------
    {
        "id": "purchasing",
        "label": "Purchasing",
        "icon": "fas fa-shopping-cart",
        "roles": ["purchasing", "warehouse", "ops", "supervisor", "manager", "admin"],
        "items": [
            {
                "id": "purchasing_manager",
                "label": "Command Center",
                "endpoint": "purchasing.manager_dashboard",
                "icon": "fas fa-chart-line",
                "description": "Manager dashboard across branches, buyers, and supplier risk.",
                "roles": ["manager", "ops", "supervisor", "admin"],
                "permissions": ["purchasing.dashboard.view"],
            },
            {
                "id": "purchasing_workspace",
                "label": "Buyer Workspace",
                "endpoint": "purchasing.buyer_dashboard",
                "icon": "fas fa-briefcase",
                "description": "Daily buyer queue, priorities, and suggested buys.",
                "roles": ["purchasing", "manager", "ops", "supervisor", "admin"],
                "permissions": ["purchasing.branch.view"],
            },
            {
                "id": "purchasing_suggested",
                "label": "Suggested Buys",
                "endpoint": "purchasing.suggested_buys",
                "icon": "fas fa-shopping-basket",
                "description": "Review point-in-time suggested purchasing batches.",
                "roles": ["purchasing", "manager", "ops", "supervisor", "admin"],
                "permissions": ["purchasing.branch.view"],
            },
            {
                "id": "po_checkin",
                "label": "PO Check-In",
                "endpoint": "po.checkin",
                "icon": "fas fa-camera",
                "description": "Photograph and record incoming purchase orders.",
                "roles": ["purchasing", "warehouse"],
                "permissions": ["po.submit"],
            },
            {
                "id": "po_review",
                "label": "Review Submissions",
                "endpoint": "po.review_dashboard",
                "icon": "fas fa-clipboard-check",
                "description": "Review and flag PO check-in submissions.",
                "roles": ["ops", "supervisor", "admin"],
                "permissions": ["po.review"],
            },
            {
                "id": "po_open_pos",
                "label": "Open POs",
                "endpoint": "po.open_pos",
                "icon": "fas fa-list-alt",
                "description": "Browse open purchase orders and receiving status.",
                "roles": ["supervisor", "admin"],
                "permissions": ["po.open_pos"],
            },
        ],
    },
    # ------------------------------------------------------------------
    # ADMIN
    # ------------------------------------------------------------------
    {
        "id": "admin",
        "label": "Admin",
        "icon": "fas fa-cog",
        "roles": ["admin"],
        "items": [
            {
                "id": "work_center",
                "label": "App Home",
                "endpoint": "main.work_center",
                "icon": "fas fa-home",
                "description": "Choose the workflow that matches the job at hand.",
                "roles": ["*"],
                "permissions": ["nav.home"],
            },
            {
                "id": "admin_users",
                "label": "User & Role Management",
                "endpoint": "main.admin",
                "icon": "fas fa-users-cog",
                "description": "Manage warehouse pickers and role assignments.",
                "roles": ["admin"],
                "permissions": ["admin.users"],
            },
            {
                "id": "auth_users",
                "label": "Login Accounts",
                "endpoint": "auth.manage_users",
                "icon": "fas fa-id-badge",
                "description": "Add users, assign rep IDs, and control access roles.",
                "roles": ["admin"],
                "permissions": ["admin.auth"],
            },
            {
                "id": "legacy_dashboard",
                "label": "Legacy Dashboard",
                "endpoint": "main.dashboard",
                "icon": "fas fa-columns",
                "description": "Keep legacy operational dashboards reachable.",
                "roles": ["admin", "ops"],
                "permissions": ["dashboard.view"],
            },
        ],
    },
]


PUBLIC_MENU_FALLBACK = ["*"]


def _normalize_claims(values: Iterable[str] | None) -> set[str]:
    normalized = {str(value).strip().lower() for value in (values or []) if str(value).strip()}
    return normalized or {"*"}


def _is_allowed(required_roles: Iterable[str] | None, user_roles: set[str]) -> bool:
    # admin always sees everything — mirrors the same bypass in auth.py
    if "admin" in user_roles:
        return True
    role_set = _normalize_claims(required_roles)
    return "*" in role_set or "*" in user_roles or bool(role_set & user_roles)


def get_current_user_roles() -> list[str]:
    session_roles = session.get("user_roles")
    if isinstance(session_roles, (list, tuple, set)) and session_roles:
        return [str(role) for role in session_roles]

    config_roles = current_app.config.get("NAV_DEFAULT_ROLES")
    if isinstance(config_roles, (list, tuple, set)) and config_roles:
        return [str(role) for role in config_roles]

    return PUBLIC_MENU_FALLBACK.copy()


def build_navigation(user_roles: Iterable[str] | None = None) -> list[dict]:
    active_endpoint = request.endpoint
    normalized_roles = _normalize_claims(user_roles or get_current_user_roles())
    sections: list[dict] = []

    for section in deepcopy(NAV_SECTIONS):
        if not _is_allowed(section.get("roles"), normalized_roles):
            continue

        visible_items = []
        for item in section.get("items", []):
            if not _is_allowed(item.get("roles"), normalized_roles):
                continue

            item["href"] = url_for(item["endpoint"])
            item["is_active"] = active_endpoint == item["endpoint"]
            visible_items.append(item)

        # Include section if it has visible items OR is marked coming_soon
        if visible_items or section.get("coming_soon"):
            section["items"] = visible_items
            section["has_active_item"] = any(item["is_active"] for item in visible_items)
            sections.append(section)

    return sections
