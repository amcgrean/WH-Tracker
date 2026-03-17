(function () {
  const state = {
    showLegend: false,
    map: null,
    layer: null,
    refreshSec: 20,
    apiBase: '',
    colors: {},
    colorList: [],
    branches: [],
    lastFetchedAt: null,
    onStatus: null,
    legend: null,
    branchFilter: [],
    inFlight: false,
    abort: null,
    isRunning: false,
    visibilityHandlerAdded: false,
  };

  const DEFAULT_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
    '#9467bd', '#8c564b', '#e377c2', '#7f7f7f',
    '#bcbd22', '#17becf'
  ];

  function pickColorFor(branch) {
    const key = (branch || 'UNASSIGNED').toUpperCase();
    if (state.colors[key]) return state.colors[key];
    const idx = Object.keys(state.colors).length % state.colorList.length;
    state.colors[key] = state.colorList[idx];
    return state.colors[key];
  }

  async function loadBranches() {
    try {
      const res = await fetch(`${state.apiBase}/api/branches`);
      if (!res.ok) throw new Error(`branches http ${res.status}`);
      state.branches = await res.json();
      state.branches.forEach((branch, i) => {
        const code = String(branch.code || 'UNASSIGNED').toUpperCase();
        if (!state.colors[code]) state.colors[code] = state.colorList[i % state.colorList.length];
      });
      renderLegend();
    } catch (_error) {
      renderLegend();
    }
  }

  function renderLegend() {
    if (!state.map || !state.showLegend) return;
    if (state.legend) {
      state.map.removeControl(state.legend);
      state.legend = null;
    }
    const entries = Object.entries(state.colors);
    if (!entries.length) return;

    const ctrl = L.control({ position: 'bottomright' });
    ctrl.onAdd = function () {
      const div = L.DomUtil.create('div', 'vehicles-legend');
      div.style.background = 'white';
      div.style.padding = '8px 10px';
      div.style.borderRadius = '8px';
      div.style.boxShadow = '0 2px 8px rgba(0,0,0,0.15)';

      const title = document.createElement('div');
      title.textContent = 'Vehicles';
      title.style.fontWeight = '600';
      title.style.marginBottom = '8px';
      div.appendChild(title);

      entries.forEach(([branch, color]) => {
        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.alignItems = 'center';
        row.style.gap = '8px';
        row.style.margin = '2px 0';

        const swatch = document.createElement('span');
        swatch.style.display = 'inline-block';
        swatch.style.width = '12px';
        swatch.style.height = '12px';
        swatch.style.borderRadius = '50%';
        swatch.style.background = color;
        row.appendChild(swatch);

        const label = document.createElement('span');
        label.textContent = branch;
        row.appendChild(label);
        div.appendChild(row);
      });

      return div;
    };
    ctrl.addTo(state.map);
    state.legend = ctrl;
  }

  function clearLayer() {
    if (state.layer) state.layer.clearLayers();
  }

  function vehicleMarkerFor(vehicle) {
    const color = pickColorFor(vehicle.branch);
    const heading = vehicle.heading != null ? +vehicle.heading : 0;
    const html = `
      <div style="display:flex; flex-direction:column; align-items:center;">
        <div style="transform: rotate(${heading}deg); transform-origin: center center;">
          <svg width="34" height="28" viewBox="0 0 34 28">
            <rect x="4" y="7" width="20" height="12" rx="3" fill="${color}" stroke="#ffffff" stroke-width="2"/>
            <rect x="20" y="9" width="8" height="8" rx="2" fill="${color}" stroke="#ffffff" stroke-width="2"/>
            <rect x="21.5" y="10.5" width="5" height="4.5" rx="1" fill="rgba(255,255,255,.4)"/>
            <circle cx="11" cy="21" r="3" fill="#1f2937" stroke="#ffffff" stroke-width="2"/>
            <circle cx="24" cy="21" r="3" fill="#1f2937" stroke="#ffffff" stroke-width="2"/>
            <rect x="2" y="11" width="3" height="4" rx="1" fill="#f8fafc"/>
            <polygon points="30,14 33,11 33,17" fill="${color}" stroke="#ffffff" stroke-width="1.5" stroke-linejoin="round"/>
          </svg>
        </div>
        <div style="margin-top:2px; padding:1px 4px; border-radius:4px; background:rgba(255,255,255,0.85); font-size:11px; line-height:1; white-space:nowrap;">
          ${vehicle.name || vehicle.id}
        </div>
      </div>
    `;

    const icon = L.divIcon({
      className: 'veh-tri',
      html,
      iconSize: [60, 38],
      iconAnchor: [30, 26],
    });

    const marker = L.marker([vehicle.lat, vehicle.lon], { icon }).bindPopup(`
      <div style="min-width:220px">
        <div style="font-weight:700;">${vehicle.name || vehicle.id}</div>
        ${vehicle.branch ? `<div>Branch: <b>${vehicle.branch}</b></div>` : ''}
        <div>${vehicle.speed != null ? `Speed: ${Math.round(vehicle.speed)} mph` : ''} ${vehicle.heading != null ? `• ${Math.round(vehicle.heading)}°` : ''}</div>
        <div>${vehicle.located_at ? `Last seen: ${new Date(vehicle.located_at).toLocaleString()}` : ''}</div>
      </div>
    `);
    marker.on('click', () => {
      document.dispatchEvent(new CustomEvent('dispatch:vehicle-selected', { detail: vehicle }));
    });
    return marker;
  }

  function renderVehicles(vehicles) {
    if (!state.layer) state.layer = L.layerGroup().addTo(state.map);
    clearLayer();
    vehicles.forEach((vehicle) => {
      if (typeof vehicle.lat !== 'number' || typeof vehicle.lon !== 'number') return;
      vehicleMarkerFor(vehicle).addTo(state.layer);
    });

    if (state.showLegend) renderLegend();

    if (state.onStatus) {
      const count = vehicles.length;
      const timestamp = state.lastFetchedAt ? new Date(state.lastFetchedAt).toLocaleTimeString() : '';
      state.onStatus(`${count} vehicles${timestamp ? ` • live ${timestamp}` : ''}`);
    }
  }

  function setBranch(codeOrList) {
    if (!codeOrList) state.branchFilter = [];
    else if (Array.isArray(codeOrList)) state.branchFilter = codeOrList.map((value) => String(value).toUpperCase());
    else if (String(codeOrList).includes(',')) state.branchFilter = String(codeOrList).split(',').map((value) => value.trim().toUpperCase()).filter(Boolean);
    else state.branchFilter = [String(codeOrList).toUpperCase()];
    if (state.isRunning) setTimeout(tickLoop, 0);
  }

  async function fetchLive() {
    const params = new URLSearchParams();
    const branchParam = Array.isArray(state.branchFilter) && state.branchFilter.length === 1 ? state.branchFilter[0] : '';
    if (branchParam) params.set('branch', branchParam);
    params.set('limit', '100');

    if (state.abort) {
      try { state.abort.abort(); } catch (_error) {}
      state.abort = null;
    }
    state.abort = new AbortController();

    const res = await fetch(`${state.apiBase}/api/vehicles/live?${params.toString()}`, { signal: state.abort.signal });
    if (!res.ok) throw new Error(`vehicles http ${res.status}`);

    const data = await res.json();
    state.lastFetchedAt = data.fetched_at || null;
    let vehicles = data.vehicles || [];

    if (Array.isArray(state.branchFilter) && state.branchFilter.length) {
      const wanted = new Set(state.branchFilter.map((value) => String(value).toUpperCase()));
      vehicles = vehicles.filter((vehicle) => wanted.has(String(vehicle.branch || '').toUpperCase()));
    }
    return vehicles;
  }

  async function tickLoop() {
    if (!state.isRunning) return;
    if (state.refreshSec === 0) {
      if (state.onStatus && state.lastFetchedAt) {
        state.onStatus(`vehicles paused • last ${new Date(state.lastFetchedAt).toLocaleTimeString()}`);
      } else if (state.onStatus) {
        state.onStatus('vehicles paused');
      }
      setTimeout(tickLoop, 2000);
      return;
    }
    if (document.hidden) {
      setTimeout(tickLoop, Math.max(1000, state.refreshSec * 1000));
      return;
    }
    if (state.inFlight) {
      setTimeout(tickLoop, 500);
      return;
    }

    state.inFlight = true;
    try {
      const vehicles = await fetchLive();
      renderVehicles(vehicles);
      setTimeout(tickLoop, Math.max(1000, state.refreshSec * 1000));
    } catch (_error) {
      if (state.onStatus) state.onStatus('vehicles: update failed');
      setTimeout(tickLoop, 10000);
    } finally {
      state.inFlight = false;
    }
  }

  function start() {
    if (state.isRunning) return;
    state.isRunning = true;
    if (!state.visibilityHandlerAdded) {
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden && state.isRunning) setTimeout(tickLoop, 0);
      });
      state.visibilityHandlerAdded = true;
    }
    setTimeout(tickLoop, 0);
  }

  function stop() {
    state.isRunning = false;
    state.inFlight = false;
    if (state.abort) {
      try { state.abort.abort(); } catch (_error) {}
      state.abort = null;
    }
  }

  function init(opts) {
    const { map, apiBase = '', refreshSec = 20, onStatus = null, palette = DEFAULT_COLORS, legend = false } = opts || {};
    if (!map) throw new Error('VehiclesOverlay.init requires { map }');
    state.map = map;
    state.apiBase = apiBase;
    state.refreshSec = refreshSec;
    state.onStatus = onStatus;
    state.colorList = Array.isArray(palette) && palette.length ? palette.slice() : DEFAULT_COLORS.slice();
    state.layer = L.layerGroup().addTo(map);
    state.showLegend = !!legend;
    loadBranches();
  }

  function setRefreshSec(value) {
    const parsed = Number(value);
    state.refreshSec = Number.isFinite(parsed) && parsed >= 0 ? parsed : 20;
    if (state.isRunning) setTimeout(tickLoop, 0);
  }

  window.VehiclesOverlay = { init, start, stop, setBranch, setRefreshSec, _state: state };
})();
