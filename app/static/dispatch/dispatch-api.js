/**
 * API client for the dispatch console.
 * All fetch calls centralized here.
 */

const BASE = window.DISPATCH_API_BASE || '/dispatch';

async function fetchJSON(url, options = {}) {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: resp.statusText }));
    throw new Error(err.error || resp.statusText);
  }
  return resp.json();
}

// ── Stops ──
export function loadEnrichedStops(params) {
  const qs = new URLSearchParams();
  if (params.start) qs.set('start', params.start);
  if (params.end) qs.set('end', params.end);
  if (params.branch) qs.set('branch', params.branch);
  if (params.status) qs.set('status', params.status);
  return fetchJSON(`${BASE}/api/stops/enriched?${qs}`);
}

export function loadStops(params) {
  const qs = new URLSearchParams();
  if (params.start) qs.set('start', params.start);
  if (params.end) qs.set('end', params.end);
  if (params.branch) qs.set('branch', params.branch);
  return fetchJSON(`${BASE}/api/stops?${qs}`);
}

// ── KPIs ──
export function loadKPIs(date, branch) {
  const qs = new URLSearchParams();
  if (date) qs.set('date', date);
  if (branch) qs.set('branch', branch);
  return fetchJSON(`${BASE}/api/kpis?${qs}`);
}

// ── Routes ──
export function loadRoutes(date, branch) {
  const qs = new URLSearchParams();
  if (date) qs.set('date', date);
  if (branch) qs.set('branch', branch);
  return fetchJSON(`${BASE}/api/routes?${qs}`);
}

export function createRoute(data) {
  return fetchJSON(`${BASE}/api/routes`, {
    method: 'POST', body: JSON.stringify(data),
  });
}

export function updateRoute(routeId, data) {
  return fetchJSON(`${BASE}/api/routes/${routeId}`, {
    method: 'PUT', body: JSON.stringify(data),
  });
}

export function deleteRoute(routeId) {
  return fetchJSON(`${BASE}/api/routes/${routeId}`, { method: 'DELETE' });
}

export function addStopsToRoute(routeId, stops) {
  return fetchJSON(`${BASE}/api/routes/${routeId}/stops`, {
    method: 'POST', body: JSON.stringify({ stops }),
  });
}

export function reorderStops(routeId, stopIds) {
  return fetchJSON(`${BASE}/api/routes/${routeId}/stops/reorder`, {
    method: 'PUT', body: JSON.stringify({ stop_ids: stopIds }),
  });
}

export function removeStop(routeId, stopId) {
  return fetchJSON(`${BASE}/api/routes/${routeId}/stops/${stopId}`, {
    method: 'DELETE',
  });
}

// ── Drivers ──
export function loadDrivers(branch) {
  const qs = branch ? `?branch=${encodeURIComponent(branch)}` : '';
  return fetchJSON(`${BASE}/api/drivers${qs}`);
}

export function createDriver(data) {
  return fetchJSON(`${BASE}/api/drivers`, {
    method: 'POST', body: JSON.stringify(data),
  });
}

export function updateDriver(driverId, data) {
  return fetchJSON(`${BASE}/api/drivers/${driverId}`, {
    method: 'PUT', body: JSON.stringify(data),
  });
}

export function seedDriversFromERP(branch) {
  const qs = branch ? `?branch=${encodeURIComponent(branch)}` : '';
  return fetchJSON(`${BASE}/api/drivers/seed-from-erp${qs}`, { method: 'POST' });
}

// ── Trucks ──
export function loadTrucks(date, branch) {
  const qs = new URLSearchParams();
  if (date) qs.set('date', date);
  if (branch) qs.set('branch', branch);
  return fetchJSON(`${BASE}/api/trucks?${qs}`);
}

export function upsertTruckAssignment(data) {
  return fetchJSON(`${BASE}/api/trucks/assignments`, {
    method: 'POST', body: JSON.stringify(data),
  });
}

export function copyPreviousAssignments(targetDate, branch) {
  return fetchJSON(`${BASE}/api/trucks/assignments/copy-previous`, {
    method: 'POST',
    body: JSON.stringify({ target_date: targetDate, branch }),
  });
}

// ── Order Detail ──
export function loadOrderLines(soId, shipmentNum) {
  const qs = shipmentNum != null ? `?shipment_num=${shipmentNum}` : '';
  return fetchJSON(`${BASE}/api/orders/${soId}/lines${qs}`);
}

export function loadOrderTimeline(soId) {
  return fetchJSON(`${BASE}/api/orders/${soId}/timeline`);
}

export function loadOrderWorkOrders(soId) {
  return fetchJSON(`${BASE}/api/orders/${soId}/work-orders`);
}

export function loadCustomerSummary(custKey) {
  return fetchJSON(`${BASE}/api/customers/${encodeURIComponent(custKey)}/summary`);
}

// ── Manifest ──
export function generateManifest(items) {
  return fetch(`${BASE}/api/manifest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  }).then(resp => {
    if (!resp.ok) throw new Error('Manifest generation failed');
    return resp.blob();
  });
}

// ── Vehicles ──
export function loadVehicles(branch) {
  const qs = branch ? `?branch=${encodeURIComponent(branch)}` : '';
  return fetchJSON(`${BASE}/api/vehicles/live${qs}`);
}
