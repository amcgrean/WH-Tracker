/**
 * Route panel: unassigned stops list, route cards with drag-drop.
 */
import { on, emit, getState, setState, getUnassignedStops, getFilteredStops } from './dispatch-state.js';
import * as api from './dispatch-api.js';

const ROUTE_COLORS = [
  '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
  '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
];

let panelBody;

export function init() {
  panelBody = document.getElementById('routePanelBody');

  // Tab switching
  document.querySelectorAll('.route-panel-tabs .tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.route-panel-tabs .tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      setState({ activeTab: tab.dataset.tab });
      render();
    });
  });

  // New route button
  document.getElementById('btnNewRoute').addEventListener('click', handleNewRoute);

  // Listen for data updates
  on('stops-loaded', render);
  on('routes-loaded', render);
  on('search-changed', render);
  on('selection-changed', render);
}

function render() {
  const state = getState();
  const tab = state.activeTab;

  if (tab === 'unassigned') {
    renderUnassigned();
  } else if (tab === 'routes') {
    renderRoutes();
  } else {
    renderAllStops();
  }
}

function renderUnassigned() {
  const unassigned = getFilteredStops(getUnassignedStops());
  const state = getState();

  panelBody.innerHTML = `
    <div style="padding:6px 12px; font-size:11px; color:#888; border-bottom:1px solid #f0f0f0;">
      ${unassigned.length} unassigned stop${unassigned.length !== 1 ? 's' : ''}
    </div>
    <ul class="stop-list" id="unassignedList">
      ${unassigned.map(s => stopItemHTML(s, state)).join('')}
    </ul>
  `;

  // Bind click handlers
  panelBody.querySelectorAll('.stop-item').forEach(el => {
    const soId = el.dataset.soId;
    el.addEventListener('click', e => {
      if (e.shiftKey) {
        // Multi-select
        const sel = getState().selectedStopIds;
        if (sel.has(soId)) sel.delete(soId); else sel.add(soId);
        setState({ selectedStopIds: sel });
      } else {
        setState({ selectedStopId: soId, selectedStopIds: new Set([soId]) });
      }
      emit('selection-changed', { soId });
      emit('stop-selected', soId);
    });

    el.addEventListener('dblclick', () => {
      setState({ selectedStopId: soId });
      emit('stop-selected', soId);
      emit('detail-open', soId);
    });

    // Drag
    el.draggable = true;
    el.addEventListener('dragstart', e => {
      e.dataTransfer.setData('text/plain', JSON.stringify({ so_id: soId, shipment_num: el.dataset.shipmentNum }));
      el.classList.add('dragging');
    });
    el.addEventListener('dragend', () => el.classList.remove('dragging'));
  });
}

function renderRoutes() {
  const state = getState();
  const routes = state.routes;

  if (!routes.length) {
    panelBody.innerHTML = '<div style="padding:20px; text-align:center; color:#aaa; font-size:13px;">No routes for this date. Click "+ New Route" to create one.</div>';
    return;
  }

  panelBody.innerHTML = routes.map((r, i) => routeCardHTML(r, i)).join('');

  // Bind route card interactions
  panelBody.querySelectorAll('.route-card-header').forEach(header => {
    header.addEventListener('click', () => {
      const card = header.closest('.route-card');
      card.classList.toggle('expanded');
      const routeId = parseInt(card.dataset.routeId);
      setState({ selectedRouteId: routeId });
      emit('route-selected', routeId);
    });
  });

  // Drop zones
  panelBody.querySelectorAll('.route-drop-zone').forEach(zone => {
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', async e => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      const routeId = parseInt(zone.dataset.routeId);
      try {
        const data = JSON.parse(e.dataTransfer.getData('text/plain'));
        await api.addStopsToRoute(routeId, [data]);
        emit('routes-reload', {});
      } catch (err) {
        console.error('Drop failed:', err);
      }
    });
  });

  // Route stop drag reorder
  panelBody.querySelectorAll('.route-stop-item').forEach(item => {
    item.draggable = true;
    item.addEventListener('dragstart', e => {
      e.dataTransfer.setData('application/route-stop', JSON.stringify({
        stopId: item.dataset.stopId,
        routeId: item.dataset.routeId,
      }));
    });
  });

  // Delete route buttons
  panelBody.querySelectorAll('.btn-delete-route').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      const routeId = parseInt(btn.dataset.routeId);
      if (confirm('Delete this route?')) {
        await api.deleteRoute(routeId);
        emit('routes-reload', {});
      }
    });
  });

  // Remove stop buttons
  panelBody.querySelectorAll('.btn-remove-stop').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      const routeId = parseInt(btn.dataset.routeId);
      const stopId = parseInt(btn.dataset.stopId);
      await api.removeStop(routeId, stopId);
      emit('routes-reload', {});
    });
  });
}

function renderAllStops() {
  const all = getFilteredStops(getState().stops);
  const state = getState();

  panelBody.innerHTML = `
    <div style="padding:6px 12px; font-size:11px; color:#888; border-bottom:1px solid #f0f0f0;">
      ${all.length} total stop${all.length !== 1 ? 's' : ''}
    </div>
    <ul class="stop-list">
      ${all.map(s => stopItemHTML(s, state)).join('')}
    </ul>
  `;

  panelBody.querySelectorAll('.stop-item').forEach(el => {
    el.addEventListener('click', () => {
      setState({ selectedStopId: el.dataset.soId });
      emit('selection-changed', { soId: el.dataset.soId });
      emit('stop-selected', el.dataset.soId);
    });
    el.addEventListener('dblclick', () => {
      emit('detail-open', el.dataset.soId);
    });
  });
}

function stopItemHTML(s, state) {
  const selected = state.selectedStopIds.has(String(s.id)) || state.selectedStopId === String(s.id);
  const pickClass = s.pick_status === 'picked' ? 'picked' : s.pick_status === 'partial' ? 'partial' : 'not-picked';
  const city = (s.address || '').split(',').pop()?.trim() || '';
  return `
    <li class="stop-item${selected ? ' selected' : ''}" data-so-id="${s.id}" data-shipment-num="${s.shipment_num || ''}">
      <span class="pick-dot ${pickClass}" title="${s.pick_status || 'unknown'}"></span>
      <span class="stop-name" title="${s.shipto_name || ''}">${s.shipto_name || s.id}</span>
      <span class="stop-meta">
        ${city ? `<span>${city}</span>` : ''}
        ${s.order_value ? `<span class="badge-sm badge-value">$${formatNum(s.order_value)}</span>` : ''}
        ${s.total_weight ? `<span class="badge-sm badge-weight">${formatNum(s.total_weight)} lb</span>` : ''}
        ${s.credit_hold ? '<span class="badge-sm badge-credit-hold">HOLD</span>' : ''}
        <span>${s.item_count || 0} items</span>
      </span>
    </li>
  `;
}

function routeCardHTML(route, index) {
  const color = ROUTE_COLORS[index % ROUTE_COLORS.length];
  const stops = route.stops || [];
  const totalWeight = stops.reduce((sum, s) => sum + (s.total_weight || 0), 0);
  const statusClass = `status-${route.status}`;

  return `
    <div class="route-card" data-route-id="${route.id}">
      <div class="route-card-header">
        <div class="route-card-color" style="background:${color}"></div>
        <div class="route-card-info">
          <div class="route-card-name">${escapeHTML(route.route_name)}</div>
          <div class="route-card-meta">
            ${route.driver_name ? route.driver_name + ' &middot; ' : ''}
            ${stops.length} stop${stops.length !== 1 ? 's' : ''}
            ${totalWeight ? ' &middot; ' + formatNum(totalWeight) + ' lb' : ''}
          </div>
        </div>
        <span class="route-card-status ${statusClass}">${route.status}</span>
        ${route.status === 'draft' ? `<button class="btn-delete-route" data-route-id="${route.id}" title="Delete route" style="background:none;border:none;color:#d62728;cursor:pointer;font-size:14px;">&times;</button>` : ''}
      </div>
      <div class="route-card-body">
        <ul class="stop-list-route">
          ${stops.map((s, i) => `
            <li class="route-stop-item" data-stop-id="${s.id}" data-route-id="${route.id}">
              <span class="route-stop-seq">${i + 1}</span>
              <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${s.so_id}</span>
              <button class="btn-remove-stop" data-route-id="${route.id}" data-stop-id="${s.id}" style="background:none;border:none;color:#999;cursor:pointer;font-size:12px;" title="Remove">&times;</button>
            </li>
          `).join('')}
        </ul>
        <div class="route-drop-zone" data-route-id="${route.id}">Drop stops here to add</div>
      </div>
    </div>
  `;
}

async function handleNewRoute() {
  const state = getState();
  const name = prompt('Route name:');
  if (!name) return;
  const branch = state.branch || '20GR';
  await api.createRoute({
    route_date: state.date,
    route_name: name,
    branch_code: branch,
  });
  emit('routes-reload', {});
}

function formatNum(n) {
  if (n == null) return '';
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function escapeHTML(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

export { ROUTE_COLORS };
