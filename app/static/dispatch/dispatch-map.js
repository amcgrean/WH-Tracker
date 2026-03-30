/**
 * Map module: Leaflet map, stop markers, route polylines, vehicle overlay.
 */
import { on, emit, getState, setState } from './dispatch-state.js';
import { ROUTE_COLORS } from './dispatch-route-panel.js';

let map;
let stopLayer;
let routeLineLayer;
let markers = {};  // soId → marker

const UNASSIGNED_COLOR = '#999';

export function init() {
  map = L.map('map', {
    center: [41.68, -93.57],  // Des Moines area default
    zoom: 10,
    zoomControl: true,
  });

  // Street tiles
  const street = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap',
    maxZoom: 19,
  });

  const sat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: '&copy; Esri',
    maxZoom: 19,
  });

  const basemap = getState().settings.basemap;
  (basemap === 'sat' ? sat : street).addTo(map);

  stopLayer = L.layerGroup().addTo(map);
  routeLineLayer = L.layerGroup().addTo(map);

  // Initialize vehicle overlay (loaded as global IIFE)
  if (window.VehiclesOverlay) {
    window.VehiclesOverlay.init({
      map,
      apiBase: window.DISPATCH_API_BASE || '/dispatch',
      refreshSec: getState().settings.refreshSec || 20,
      onStatus: text => {
        const el = document.getElementById('vehicleStatus');
        if (el) el.textContent = text;
      },
      legend: false,
    });
    window.VehiclesOverlay.start();
  }

  // Listen for events
  on('stops-loaded', renderStopMarkers);
  on('routes-loaded', renderRouteLines);
  on('selection-changed', highlightSelected);
  on('route-selected', highlightRoute);
  on('stop-selected', panToStop);

  on('settings-changed', settings => {
    if (window.VehiclesOverlay) {
      window.VehiclesOverlay.setRefreshSec(settings.refreshSec || 20);
    }
  });

  on('filters-changed', state => {
    if (window.VehiclesOverlay && state.branch) {
      window.VehiclesOverlay.setBranch(state.branch);
    }
  });
}

export function getMap() {
  return map;
}

function renderStopMarkers() {
  const state = getState();
  const stops = state.stops;
  stopLayer.clearLayers();
  markers = {};

  // Build route assignment map: soId → routeIndex
  const routeMap = {};
  state.routes.forEach((r, i) => {
    (r.stops || []).forEach(s => {
      routeMap[String(s.so_id)] = i;
    });
  });

  const bounds = [];

  stops.forEach(s => {
    if (typeof s.lat !== 'number' || typeof s.lon !== 'number') return;

    const routeIdx = routeMap[String(s.id)];
    const color = routeIdx != null ? ROUTE_COLORS[routeIdx % ROUTE_COLORS.length] : UNASSIGNED_COLOR;
    const selected = state.selectedStopId === String(s.id);

    const icon = L.divIcon({
      className: 'dispatch-stop-marker',
      html: `<div style="
        width:${selected ? 16 : 12}px; height:${selected ? 16 : 12}px;
        border-radius:50%; background:${color};
        border:2px solid #fff; box-shadow:0 1px 4px rgba(0,0,0,0.3);
        ${selected ? 'outline:3px solid ' + color + '40;' : ''}
      "></div>`,
      iconSize: [selected ? 20 : 16, selected ? 20 : 16],
      iconAnchor: [selected ? 10 : 8, selected ? 10 : 8],
    });

    const marker = L.marker([s.lat, s.lon], { icon });
    marker.bindPopup(`
      <div style="min-width:180px; font-size:12px;">
        <strong>${escapeHTML(s.shipto_name || s.id)}</strong><br>
        ${s.address ? `<span style="color:#666;">${escapeHTML(s.address)}</span><br>` : ''}
        ${s.order_value ? `Value: $${Number(s.order_value).toLocaleString()}<br>` : ''}
        ${s.total_weight ? `Weight: ${Number(s.total_weight).toLocaleString()} lb<br>` : ''}
        ${s.item_count ? `Items: ${s.item_count}` : ''}
      </div>
    `);

    marker.on('click', () => {
      setState({ selectedStopId: String(s.id), selectedStopIds: new Set([String(s.id)]) });
      emit('selection-changed', { soId: String(s.id) });
      emit('stop-selected', String(s.id));
    });

    marker.on('dblclick', () => {
      emit('detail-open', String(s.id));
    });

    marker.addTo(stopLayer);
    markers[String(s.id)] = marker;
    bounds.push([s.lat, s.lon]);
  });

  // Fit bounds if we have markers
  if (bounds.length) {
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
  }

  updateLegend(state);
}

function renderRouteLines() {
  routeLineLayer.clearLayers();
  const state = getState();

  state.routes.forEach((route, i) => {
    const stops = route.stops || [];
    const color = ROUTE_COLORS[i % ROUTE_COLORS.length];
    const coords = [];

    stops.forEach(s => {
      // Find matching stop data for lat/lon
      const full = state.stops.find(st => String(st.id) === String(s.so_id));
      if (full && typeof full.lat === 'number' && typeof full.lon === 'number') {
        coords.push([full.lat, full.lon]);
      }
    });

    if (coords.length >= 2) {
      L.polyline(coords, {
        color,
        weight: 3,
        opacity: 0.7,
        dashArray: '8, 6',
      }).addTo(routeLineLayer);
    }
  });
}

function highlightSelected(data) {
  // Re-render to update marker sizes
  renderStopMarkers();
}

function highlightRoute(routeId) {
  const state = getState();
  const route = state.routes.find(r => r.id === routeId);
  if (!route || !route.stops?.length) return;

  const coords = [];
  route.stops.forEach(s => {
    const full = state.stops.find(st => String(st.id) === String(s.so_id));
    if (full && typeof full.lat === 'number' && typeof full.lon === 'number') {
      coords.push([full.lat, full.lon]);
    }
  });

  if (coords.length) {
    map.fitBounds(coords, { padding: [60, 60], maxZoom: 14 });
  }
}

function panToStop(soId) {
  const marker = markers[String(soId)];
  if (marker) {
    map.setView(marker.getLatLng(), Math.max(map.getZoom(), 13), { animate: true });
    marker.openPopup();
  }
}

function updateLegend(state) {
  const el = document.getElementById('mapLegendContent');
  if (!el) return;

  const items = [];
  items.push(`<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">
    <span style="width:10px;height:10px;border-radius:50%;background:${UNASSIGNED_COLOR};display:inline-block;"></span>
    <span>Unassigned</span>
  </div>`);

  state.routes.forEach((r, i) => {
    const color = ROUTE_COLORS[i % ROUTE_COLORS.length];
    items.push(`<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">
      <span style="width:10px;height:10px;border-radius:50%;background:${color};display:inline-block;"></span>
      <span>${escapeHTML(r.route_name)}</span>
    </div>`);
  });

  el.innerHTML = items.join('');
}

function escapeHTML(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}
