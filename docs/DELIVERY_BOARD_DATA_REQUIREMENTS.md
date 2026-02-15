# Delivery Board - API & ERP Data Requirements

This document outlines all data sources, API calls, and ERP queries required for the
Delivery Board feature, including the fleet map TV display.

---

## 1. Samsara Fleet Management API

**Base URL:** `https://api.samsara.com`
**Auth:** Bearer token via `SAMSARA_API_TOKEN` environment variable
**Docs:** https://developers.samsara.com/reference

### Required Endpoints

| Endpoint | Method | Purpose | Used By |
|---|---|---|---|
| `/fleet/vehicles` | GET | List all fleet vehicles (name, VIN, serial) | Vehicle inventory, dropdown selectors |
| `/fleet/vehicles/locations` | GET | Real-time GPS coordinates for all vehicles | Fleet Map (TV), Delivery Board fleet table |
| `/fleet/vehicles/{id}/locations` | GET | GPS location for a single vehicle | Delivery detail page (assigned truck) |
| `/fleet/drivers` | GET | List all drivers (name, phone, status) | Driver assignment, contact info |
| `/fleet/vehicles/stats` | GET | Engine state, fuel %, odometer | KPI cards (future enhancement) |

### Response Data Used

**Vehicle Locations** (primary data for map):
```json
{
  "data": [
    {
      "id": "vehicle-id",
      "name": "Truck 1 - Flatbed",
      "location": {
        "latitude": 41.2565,
        "longitude": -95.9345,
        "speedMilesPerHour": 35,
        "heading": 90,
        "time": "2026-02-15T14:30:00Z",
        "reverseGeo": {
          "formattedLocation": "1234 Dodge St, Omaha, NE"
        }
      }
    }
  ]
}
```

### Environment Setup

```bash
# Add to .env or Vercel environment variables
SAMSARA_API_TOKEN=your_samsara_api_token_here
```

### Rate Limits
- Samsara API: 100 requests/minute per token
- Our refresh interval: every 30s (map page), every 60s (board page)
- Well within limits for single-page polling

---

## 2. ERP (Agility SQL) Queries

**Server:** `10.1.1.17` (SQL Server via ODBC Driver 17)
**Database:** `AgilitySQL`

### 2a. Delivery Orders Query (NEW)

Fetches all open Sales Orders ready for delivery. Used on the Delivery Board main page.

```sql
SELECT
    soh.so_id,
    c.cust_name,
    cs.address_1,
    cs.city,
    soh.reference,
    COUNT(sod.sequence) as line_count
FROM so_detail sod
JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id
LEFT JOIN cust c ON soh.cust_key = c.cust_key
JOIN cust_shipto cs ON cs.cust_key = soh.cust_key AND cs.seq_num = soh.shipto_seq_num
WHERE soh.so_status = 'k'
    AND sod.bo = 0
GROUP BY soh.so_id, c.cust_name, cs.address_1, cs.city, soh.reference
ORDER BY soh.so_id
```

**Tables involved:**
- `so_header` - Sales Order header (status, customer key, reference)
- `so_detail` - Sales Order line items (item, qty, backorder flag)
- `cust` - Customer master (name)
- `cust_shipto` - Customer ship-to addresses

### 2b. SO Header Query (EXISTING - reused)

Single SO lookup for the delivery detail page.

```sql
SELECT TOP 1
    soh.so_id, c.cust_name, cs.address_1, cs.city, soh.reference
FROM so_header soh
LEFT JOIN cust c ON soh.cust_key = c.cust_key
JOIN cust_shipto cs ON cs.cust_key = soh.cust_key AND cs.seq_num = soh.shipto_seq_num
WHERE soh.so_id = ?
```

### 2c. SO Line Items Query (EXISTING - reused)

Line items for SO detail view.

```sql
SELECT
    soh.so_id, sod.sequence, i.item, i.description,
    ib.handling_code, sod.qty_ordered
FROM so_detail sod
JOIN so_header soh ON soh.so_id = sod.so_id AND sod.system_id = soh.system_id
JOIN item i ON i.item_ptr = sod.item_ptr
JOIN item_branch ib ON ib.item_ptr = sod.item_ptr AND sod.system_id = ib.system_id
WHERE soh.so_id = ? AND sod.bo = 0
ORDER BY ib.handling_code, sod.sequence
```

---

## 3. Cloud Mode (Vercel/Serverless) Fallback

When running in cloud mode (`CLOUD_MODE=True`), pyodbc is unavailable.
The delivery board falls back to the `ERPMirrorPick` SQLite table, which is
populated via the `/api/sync` endpoint from the on-premise sync script.

**Mirror table used:** `ERPMirrorPick`
**Sync endpoint:** `POST /api/sync` (requires `X-API-KEY` header)

---

## 4. Data Flow Diagram

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Samsara GPS   │     │  Agility ERP     │     │  Local SQLite    │
│   (Cloud API)   │     │  (SQL Server)    │     │  (Mirror Tables) │
└────────┬────────┘     └────────┬─────────┘     └────────┬─────────┘
         │                       │                         │
         │ GET /fleet/           │ ODBC queries            │ Fallback
         │ vehicles/locations    │                         │ (cloud mode)
         │                       │                         │
         ▼                       ▼                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Flask Routes Layer                              │
│                                                                     │
│  /delivery          → Delivery Board (KPIs + table)                │
│  /delivery/map      → Fleet Map TV Display (Leaflet.js)            │
│  /delivery/detail/# → SO Detail with line items                    │
│  /api/delivery/locations → JSON vehicle locations                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Pages & Routes Summary

| Route | Page | Data Sources | Purpose |
|---|---|---|---|
| `/delivery` | `delivery/board.html` | ERP + Samsara | Main delivery dashboard with KPIs, fleet status table, open deliveries list |
| `/delivery/map` | `delivery/map.html` | Samsara | Full-screen map for dispatch TV. Dark theme, auto-refresh 30s, Leaflet.js with CARTO dark tiles |
| `/delivery/detail/<so>` | `delivery/detail.html` | ERP | SO header, line items, truck assignment (future) |
| `/api/delivery/locations` | JSON | Samsara | API endpoint for AJAX map refresh (future enhancement) |

---

## 6. Future Enhancements (Not Yet Implemented)

These features are planned but require additional data sources or schema changes:

### 6a. Delivery Assignment & Status Tracking
- **New DB table needed:** `delivery_assignments` (so_number, truck_id, driver_id, status, dispatched_at, delivered_at)
- **Statuses:** pending → loading → in_transit → delivered
- **ERP field to investigate:** Check if `so_header` has a delivery date or ship date field (`ship_date`, `delivery_date`, `promise_date`)

### 6b. Delivery Scheduling / Route Planning
- **Samsara Routes API:** `POST /fleet/routes` - Create optimized delivery routes
- **Samsara Route Stops:** Track delivery completion at each stop
- **ERP data needed:** Promised delivery dates, time windows

### 6c. Delivery Completion from Samsara
- **Samsara Webhooks:** Configure webhook for `vehicleStopCompleted` events
- Automatically mark deliveries as complete when truck arrives at customer address

### 6d. Driver Communication
- **Samsara Messages API:** `POST /fleet/messages` - Send dispatch messages to driver tablets
- **Samsara Driver App:** Drivers can update delivery status from mobile

### 6e. Historical Delivery Metrics
- **KPIs to track:** Average delivery time, on-time %, deliveries per truck per day
- **ERP queries needed:** Historical SO with delivery dates vs. promise dates
- **Samsara History API:** `GET /fleet/vehicles/locations/history` for route replay

### 6f. Geofence Alerts
- **Samsara Geofences API:** `POST /fleet/geofences` - Set up yard geofence
- Alert when trucks leave/return to yard
- Automatic "departed yard" status update

---

## 7. ERP Fields to Investigate

The following fields in Agility SQL may contain delivery-relevant data that we haven't
yet incorporated. These should be queried in SSMS to check for useful content:

| Table | Field | Possible Use |
|---|---|---|
| `so_header` | `ship_date` | Scheduled delivery date |
| `so_header` | `promise_date` | Customer promised date |
| `so_header` | `ship_via` | Carrier / truck assignment |
| `so_header` | `freight_code` | Delivery vs. pickup indicator |
| `so_header` | `so_type` | May distinguish delivery vs. will-call |
| `so_detail` | `date_required` | Per-line delivery date |
| `cust_shipto` | `address_2`, `state`, `zip` | Full delivery address |
| `cust_shipto` | `phone` | Delivery contact phone |
| `cust_shipto` | `attention` | Delivery contact name |

---

## 8. Environment Variables Required

| Variable | Description | Required |
|---|---|---|
| `SAMSARA_API_TOKEN` | Samsara API bearer token | Yes (for live GPS data) |
| `CLOUD_MODE` | Set to `True` for serverless (disables pyodbc) | Optional |
| `SYNC_API_KEY` | API key for ERP mirror sync endpoint | For cloud mode |
| `DATABASE_URL` | Production database connection string | For production |
| `SECRET_KEY` | Flask session secret | Yes |
