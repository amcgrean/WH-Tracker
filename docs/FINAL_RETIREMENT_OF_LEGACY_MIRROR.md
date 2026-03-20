# Final Retirement of Legacy Mirror Cache - 2026-03-20

## Summary of Completion

The legacy ERP mirror system (`ERPMirrorPick`, `ERPMirrorWorkOrder`, `ERPDeliveryKPI`) has been fully retired and removed from the codebase and database.

### Completed Tasks

1.  **Code Refactor**: 
    - All remaining references to `ERPMirrorPick` and `ERPMirrorWorkOrder` in `app/Services/erp_service.py` have been replaced with normalized mirror table equivalents (`ERPMirrorPickHeaderNormalized`, `ERPMirrorWorkOrderHeader`, etc.).
    - `get_delivery_kpis` has been refactored to use historical stats from the normalized shipment header.
2.  **Sync Worker Cleanup**:
    - `sync_erp.py` no longer attempts to push data to these legacy tables. It now only reports a heartbeat status to the `erp_sync_state` table.
3.  **Model Removal**:
    - The legacy models have been deleted from `app/Models/models.py`.
    - Imports have been cleaned up in `app/__init__.py` and `app/Routes/routes.py`.
4.  **Database Cleanup**:
    - The following tables have been **dropped** from the Supabase database:
        - `erp_mirror_picks`
        - `erp_mirror_work_orders`
        - `erp_delivery_kpis`

## Verification Status

- **Smoke Tests**: `.\venv\Scripts\python.exe .\verify_route_smoke.py` passes 100%. All board and dashboard routes are functional.
- **Heartbeat**: `sync_erp.py` successfully updates its status in the database without errors.
- **Normalized Mirror**: Confirmed `CENTRAL_DB_MODE=True` is active and providing data.

## Important Context for Future Agents

- **Central Mirror**: The application is now fully dependent on the central mirror tables synced by an external process. These tables have a `Normalized` or `Header/Line` naming convention.
- **Local State**: Any future need for "local-only" pick or work order state should be handled by creating dedicated app-owned tables (like a `pick_extended` or similar) rather than trying to inject columns into the normalized mirror tables.
- **Sync Heartbeat**: The `sync_erp.py` script is still useful for reporting that the "local" environment is healthy and connected to the ERP, but it is no longer the primary data mover for these specific entities.

## Future Recommendations

- Monitor the `erp_sync_state` on the supervisor dashboard to ensure the heartbeat continues.
- If additional ERP entities are needed, they should be added to the central sync process and then mapped to models in `tracker` using the `Normalized` pattern.

**Handed off by Antigravity**
