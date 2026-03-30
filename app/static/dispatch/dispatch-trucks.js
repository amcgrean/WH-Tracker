/**
 * Truck assignment panel: Samsara vehicles merged with daily driver/route assignments.
 */
import { on, emit, getState, setState } from './dispatch-state.js';
import * as api from './dispatch-api.js';

let tbody;

export function init() {
  tbody = document.getElementById('truckTableBody');

  document.getElementById('copyYesterday').addEventListener('click', handleCopyYesterday);
  document.getElementById('seedDrivers').addEventListener('click', handleSeedDrivers);

  on('trucks-panel-opened', loadTrucks);
  on('routes-loaded', () => {
    if (getState().truckPanelOpen) renderTruckTable();
  });
  on('drivers-loaded', () => {
    if (getState().truckPanelOpen) renderTruckTable();
  });
  on('filters-changed', () => {
    if (getState().truckPanelOpen) loadTrucks();
  });
}

async function loadTrucks() {
  const state = getState();
  try {
    const [trucks, drivers] = await Promise.all([
      api.loadTrucks(state.date, state.branch),
      api.loadDrivers(state.branch),
    ]);
    setState({ trucks: trucks.assignments || trucks || [], drivers: drivers.drivers || drivers || [] });
    emit('drivers-loaded', getState().drivers);
    renderTruckTable();
    updateBadge();
  } catch (err) {
    console.error('Failed to load trucks:', err);
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#aaa;padding:12px;">Failed to load truck data</td></tr>';
  }
}

function renderTruckTable() {
  const state = getState();
  const trucks = state.trucks;
  const drivers = state.drivers;
  const routes = state.routes;

  if (!trucks.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#aaa;padding:12px;">No trucks found for this branch</td></tr>';
    return;
  }

  tbody.innerHTML = trucks.map(t => {
    const statusClass = t.speed > 0 ? 'moving' : (t.located_at && isRecent(t.located_at) ? 'idle' : 'off');
    const statusLabel = statusClass === 'moving' ? 'En Route' : statusClass === 'idle' ? 'At Yard' : 'Off';
    const lastSeen = t.located_at ? timeSince(t.located_at) : '--';

    return `<tr data-vehicle-id="${esc(t.samsara_vehicle_id || t.vehicle_id || t.id)}">
      <td><strong>${esc(t.samsara_vehicle_name || t.vehicle_name || t.name || t.id)}</strong></td>
      <td><span class="truck-status ${statusClass}"></span>${statusLabel}</td>
      <td>
        <select class="truck-driver-select" data-vehicle-id="${esc(t.samsara_vehicle_id || t.vehicle_id || t.id)}" data-vehicle-name="${esc(t.samsara_vehicle_name || t.vehicle_name || t.name || '')}">
          <option value="">— No Driver —</option>
          ${drivers.map(d => `<option value="${d.id}" ${d.id === t.driver_id ? 'selected' : ''}>${esc(d.name)}${d.phone ? ' (' + esc(d.phone) + ')' : ''}</option>`).join('')}
          <option value="__new__">+ Add Driver</option>
        </select>
      </td>
      <td>
        <select class="truck-route-select" data-vehicle-id="${esc(t.samsara_vehicle_id || t.vehicle_id || t.id)}" data-vehicle-name="${esc(t.samsara_vehicle_name || t.vehicle_name || t.name || '')}">
          <option value="">— No Route —</option>
          ${routes.map(r => `<option value="${r.id}" ${r.id === t.route_id ? 'selected' : ''}>${esc(r.route_name)}</option>`).join('')}
        </select>
      </td>
      <td style="color:#888;font-size:11px;">${lastSeen}</td>
      <td>
        <button class="truck-clear-btn" data-vehicle-id="${esc(t.samsara_vehicle_id || t.vehicle_id || t.id)}" data-vehicle-name="${esc(t.samsara_vehicle_name || t.vehicle_name || t.name || '')}" style="background:none;border:none;color:#999;cursor:pointer;font-size:12px;" title="Clear assignment">&times;</button>
      </td>
    </tr>`;
  }).join('');

  // Bind driver selects
  tbody.querySelectorAll('.truck-driver-select').forEach(sel => {
    sel.addEventListener('change', async () => {
      if (sel.value === '__new__') {
        sel.value = '';
        const name = prompt('Driver name:');
        if (!name) return;
        const phone = prompt('Phone (optional):') || '';
        try {
          const driver = await api.createDriver({ name, phone, branch_code: getState().branch });
          const newDriver = driver.driver || driver;
          const drivers = getState().drivers;
          drivers.push(newDriver);
          setState({ drivers });
          sel.value = '';
          // Save assignment with new driver
          await saveAssignment(sel.dataset.vehicleId, sel.dataset.vehicleName, newDriver.id, null);
          renderTruckTable();
        } catch (err) {
          alert('Failed to add driver: ' + err.message);
        }
        return;
      }
      await saveAssignment(sel.dataset.vehicleId, sel.dataset.vehicleName, sel.value || null, null);
    });
  });

  // Bind route selects
  tbody.querySelectorAll('.truck-route-select').forEach(sel => {
    sel.addEventListener('change', async () => {
      await saveAssignment(sel.dataset.vehicleId, sel.dataset.vehicleName, null, sel.value || null);
    });
  });

  // Bind clear buttons
  tbody.querySelectorAll('.truck-clear-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      await saveAssignment(btn.dataset.vehicleId, btn.dataset.vehicleName, '', '');
    });
  });
}

async function saveAssignment(vehicleId, vehicleName, driverId, routeId) {
  const state = getState();
  const data = {
    assignment_date: state.date,
    samsara_vehicle_id: vehicleId,
    samsara_vehicle_name: vehicleName,
    branch_code: state.branch || '',
  };
  if (driverId !== null) data.driver_id = driverId || null;
  if (routeId !== null) data.route_id = routeId || null;

  try {
    await api.upsertTruckAssignment(data);
    await loadTrucks();
  } catch (err) {
    console.error('Assignment save failed:', err);
  }
}

async function handleCopyYesterday() {
  const state = getState();
  if (!confirm('Copy truck-driver assignments from the previous working day?')) return;
  try {
    await api.copyPreviousAssignments(state.date, state.branch);
    await loadTrucks();
  } catch (err) {
    alert('Copy failed: ' + err.message);
  }
}

async function handleSeedDrivers() {
  const state = getState();
  if (!confirm('Import driver names from recent ERP shipments?')) return;
  try {
    await api.seedDriversFromERP(state.branch);
    await loadTrucks();
  } catch (err) {
    alert('Seed failed: ' + err.message);
  }
}

function updateBadge() {
  const trucks = getState().trucks;
  const assigned = trucks.filter(t => t.driver_id || t.route_id).length;
  const badge = document.getElementById('truckBadge');
  if (badge) {
    badge.textContent = trucks.length ? `(${assigned}/${trucks.length})` : '';
  }
}

function isRecent(timestamp) {
  if (!timestamp) return false;
  return (Date.now() - new Date(timestamp).getTime()) < 3600000; // 1 hour
}

function timeSince(timestamp) {
  const ms = Date.now() - new Date(timestamp).getTime();
  if (ms < 60000) return 'just now';
  if (ms < 3600000) return `${Math.floor(ms / 60000)} min ago`;
  if (ms < 86400000) return `${Math.floor(ms / 3600000)} hr ago`;
  return `${Math.floor(ms / 86400000)}d ago`;
}

function esc(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}
