/**
 * Centralized state store + event bus for the dispatch console.
 * All modules subscribe to state changes via on()/emit().
 */

const listeners = {};

export function on(event, fn) {
  (listeners[event] ||= []).push(fn);
}

export function emit(event, data) {
  (listeners[event] || []).forEach(fn => fn(data));
}

// ── Global State ──
const state = {
  // Data
  stops: [],
  routes: [],
  drivers: [],
  trucks: [],
  kpis: {},

  // Filters
  date: new Date().toISOString().slice(0, 10),
  branch: '',
  search: '',
  activeTab: 'unassigned', // unassigned | routes | all

  // Selection
  selectedStopId: null,
  selectedRouteId: null,
  selectedStopIds: new Set(), // multi-select

  // UI
  detailOpen: false,
  truckPanelOpen: false,
  settingsOpen: false,

  // Settings (persisted to localStorage)
  settings: {
    refreshSec: 30,
    defaultBranch: '',
    basemap: 'street',
    colors: { K: '#2ca02c', S: '#1f77b4', B: '#ff7f0e', CM: '#d62728' },
  },
};

export function getState() {
  return state;
}

export function setState(partial) {
  Object.assign(state, partial);
}

// ── Settings Persistence ──
const SETTINGS_KEY = 'dispatch_settings_v2';

export function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY));
    if (saved) Object.assign(state.settings, saved);
  } catch {}
  // Apply saved branch
  if (state.settings.defaultBranch) {
    state.branch = state.settings.defaultBranch;
  }
}

export function saveSettings(newSettings) {
  Object.assign(state.settings, newSettings);
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(state.settings));
  emit('settings-changed', state.settings);
}

// ── Derived Data ──
export function getUnassignedStops() {
  const assignedIds = new Set();
  for (const route of state.routes) {
    for (const stop of (route.stops || [])) {
      assignedIds.add(String(stop.so_id));
    }
  }
  return state.stops.filter(s => !assignedIds.has(String(s.id)));
}

export function getFilteredStops(stopList) {
  if (!state.search) return stopList;
  const q = state.search.toLowerCase();
  return stopList.filter(s =>
    String(s.id || '').toLowerCase().includes(q) ||
    (s.shipto_name || '').toLowerCase().includes(q) ||
    (s.customer_name || '').toLowerCase().includes(q) ||
    (s.address || '').toLowerCase().includes(q) ||
    (s.po_number || '').toLowerCase().includes(q)
  );
}
