# Centralized Agility API Agent Prompt

**Objective:** Build and maintain a centralized "Agility API" on Supabase that serves as a single source of truth for multiple frontend applications (PO-Pics, WH-Tracker, Estimating App, ToolBx), syncing data from the internal Agility ERP (SQL Server).

---

## 🏗️ Architecture Overview
- **Storage**: Supabase (PostgreSQL)
- **Source**: Agility ERP (SQL Server `10.1.1.17`, DB `AgilitySQL`)
- **Sync Mechanism**: Python scripts running on internal infrastructure (e.g., Raspberry Pi) pushing to Supabase REST API via `postgrest`.
- **Primary Auth**: Supabase Auth (JWT) with fine-grained Row Level Security (RLS) based on user roles (`worker`, `supervisor`, `estimator`).

## 📋 Domains to Implement

### 1. Purchase Orders (PO-Pics / WH-Tracker)
- **Schema**: `purchase_orders` and `purchase_order_items`.
- **Stored Procs**: `usp_GetAllOpenPOs`, `usp_GetPODetails`, `usp_GetPOItems`.
- **Requirement**: Support check-ins by workers (image uploads) and review by supervisors.
- **Sync**: Automated upsert of open POs and their line items.

### 2. Customers & Jobs (ToolBx / Estimating)
- **Schema**: `accounts` (customers), [jobs](file:///C:/Users/amcgrean/python/New%20folder/po-pics/other%20app%20files/ingest.py#396-402), `contacts`.
- **Stored Procs**: `usp_GetCustomersForPython`, `usp_GetJobsForPython`.
- **Requirement**: Link jobs to customers; serve as the backbone for invoicing and AR.

### 3. Account Receivable & Invoicing (ToolBx)
- **Schema**: `ar_transactions`, `statements`.
- **Stored Procs**: `GetARDetail`.
- **Requirement**: Ingest daily AR snapshots; provide queryable history for statements.

### 4. Products & Catalog (Estimating / WH-Tracker)
- **Schema**: `items`, `inventory_levels`, `skus`.
- **Requirement**: Sync the ERP product catalog for estimating and warehouse inventory lookups.

---

## 🛠️ Global Requirements for the API Agent

1. **Fine-Grained RLS**: Every table must have RLS enabled. Use a `profiles` table to manage roles and ensure workers only see relevant branch data, while supervisors have global or branch-wide visibility.
2. **Standardized Sync Schema**: Implement a `last_synced_at` column on all tables. Use `id` mapping consistent with ERP keys (e.g., `po_id`, `cust_key`) to ensure idempotency.
3. **API Performance**: Optimize queries for high-volume data (especially AR and Items) using PostgreSQL indexes.
4. **Integration Hooks**: Provide standard endpoints (or PostgREST configurations) that allow the `po-pics` worker app and the `WH-tracker` to share the same PO and Warehouse data.

---

## 🚀 Immediate Next Steps
- **Review Existing Schema**: Start by auditing the `po-pics` Supabase schema to ensure current work aligns with the long-term centralized goal.
- **Unified Sync Script**: Design a modular Python bridge that can be extended to include new ERP domains without starting from scratch.
- **Auth Strategy**: Formalize the `get_my_role()` and Branch-based RLS logic to be shared across all apps.
