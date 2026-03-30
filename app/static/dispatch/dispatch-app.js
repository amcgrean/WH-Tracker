/**
 * Main controller for the dispatch console.
 * Initializes all modules, loads data, manages refresh loop.
 */
import { on, emit, getState, setState, loadSettings } from './dispatch-state.js';
import * as api from './dispatch-api.js';
import * as commandBar from './dispatch-command-bar.js';
import * as routePanel from './dispatch-route-panel.js';
import * as mapModule from './dispatch-map.js';
import * as detailPanel from './dispatch-detail-panel.js';
import * as trucks from './dispatch-trucks.js';
import * as keyboard from './dispatch-keyboard.js';
import * as settings from './dispatch-settings.js';

let refreshTimer = null;

async function boot() {
  // Load persisted settings first
  loadSettings();

  // Apply saved branch to UI
  const state = getState();
  const branchEl = document.getElementById('cmdBranch');
  if (state.branch && branchEl) branchEl.value = state.branch;

  // Init all modules
  commandBar.init();
  routePanel.init();
  mapModule.init();
  detailPanel.init();
  trucks.init();
  keyboard.init();
  settings.init();

  // Core event wiring
  on('filters-changed', loadAllData);
  on('routes-reload', loadRoutes);
  on('detail-close', () => detailPanel.close());

  // Manifest print handler
  document.addEventListener('dispatch:print-manifest', async e => {
    const soId = e.detail;
    if (!soId) return;
    const stop = getState().stops.find(s => String(s.id) === String(soId));
    try {
      const blob = await api.generateManifest([{
        so_id: soId,
        shipment_num: stop?.shipment_num,
      }]);
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      console.error('Manifest failed:', err);
      alert('Manifest generation failed: ' + err.message);
    }
  });

  // Initial data load
  await loadAllData();

  // Start refresh loop
  startRefreshLoop();
}

async function loadAllData() {
  const state = getState();
  const params = {
    start: state.date,
    end: state.date,
    branch: state.branch,
  };

  try {
    const [stopsResult, routesResult, kpisResult] = await Promise.all([
      api.loadEnrichedStops(params).catch(err => {
        console.warn('Enriched stops failed, falling back:', err);
        return api.loadStops(params);
      }),
      api.loadRoutes(state.date, state.branch).catch(() => ({ routes: [] })),
      api.loadKPIs(state.date, state.branch).catch(() => ({})),
    ]);

    const stops = stopsResult.stops || stopsResult || [];
    const routes = routesResult.routes || routesResult || [];

    setState({ stops, routes, kpis: kpisResult });

    emit('stops-loaded', stops);
    emit('routes-loaded', routes);
    emit('kpis-loaded', kpisResult);
  } catch (err) {
    console.error('Data load failed:', err);
  }
}

async function loadRoutes() {
  const state = getState();
  try {
    const result = await api.loadRoutes(state.date, state.branch);
    const routes = result.routes || result || [];
    setState({ routes });
    emit('routes-loaded', routes);

    // Also refresh KPIs
    const kpis = await api.loadKPIs(state.date, state.branch).catch(() => ({}));
    setState({ kpis });
    emit('kpis-loaded', kpis);
  } catch (err) {
    console.error('Route reload failed:', err);
  }
}

function startRefreshLoop() {
  if (refreshTimer) clearInterval(refreshTimer);
  const sec = getState().settings.refreshSec || 30;
  if (sec > 0) {
    refreshTimer = setInterval(() => {
      if (!document.hidden) loadAllData();
    }, sec * 1000);
  }

  on('settings-changed', newSettings => {
    if (refreshTimer) clearInterval(refreshTimer);
    const s = newSettings.refreshSec || 30;
    if (s > 0) {
      refreshTimer = setInterval(() => {
        if (!document.hidden) loadAllData();
      }, s * 1000);
    }
  });
}

// URL hash state for bookmarking
function readHashState() {
  const hash = window.location.hash.slice(1);
  if (!hash) return;
  const params = new URLSearchParams(hash);
  const updates = {};
  if (params.get('date')) updates.date = params.get('date');
  if (params.get('branch')) updates.branch = params.get('branch');
  if (Object.keys(updates).length) {
    setState(updates);
    if (updates.date) document.getElementById('cmdDate').value = updates.date;
    if (updates.branch) document.getElementById('cmdBranch').value = updates.branch;
  }
}

function writeHashState() {
  const state = getState();
  const params = new URLSearchParams();
  if (state.date) params.set('date', state.date);
  if (state.branch) params.set('branch', state.branch);
  window.location.hash = params.toString();
}

// Wire up hash sync
on('filters-changed', writeHashState);

// Boot on DOM ready
readHashState();
boot().catch(err => console.error('Dispatch boot failed:', err));
