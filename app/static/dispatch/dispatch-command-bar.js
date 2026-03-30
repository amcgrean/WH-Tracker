/**
 * Command bar: KPI tiles, date/branch controls, search, toolbar buttons.
 */
import { on, emit, getState, setState } from './dispatch-state.js';

export function init() {
  const $ = id => document.getElementById(id);
  const state = getState();

  // Initialize date
  const dateEl = $('cmdDate');
  dateEl.value = state.date;
  dateEl.addEventListener('change', () => {
    setState({ date: dateEl.value });
    emit('filters-changed', getState());
  });

  // Branch
  const branchEl = $('cmdBranch');
  branchEl.value = state.branch;
  branchEl.addEventListener('change', () => {
    setState({ branch: branchEl.value });
    emit('filters-changed', getState());
  });

  // Load button
  $('cmdLoad').addEventListener('click', () => emit('filters-changed', getState()));

  // Search
  const searchEl = $('cmdSearch');
  let searchTimer;
  searchEl.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      setState({ search: searchEl.value });
      emit('search-changed', searchEl.value);
    }, 200);
  });

  // Truck panel toggle
  $('cmdTrucks').addEventListener('click', () => {
    const open = !getState().truckPanelOpen;
    setState({ truckPanelOpen: open });
    $('truckPanel').classList.toggle('open', open);
    $('cmdTrucks').classList.toggle('active', open);
    if (open) emit('trucks-panel-opened', {});
  });

  // Settings
  $('cmdSettings').addEventListener('click', () => emit('settings-open', {}));

  // Shortcuts
  $('cmdShortcuts').addEventListener('click', () => {
    $('shortcutsOverlay').classList.add('open');
  });

  // Listen for KPI updates
  on('kpis-loaded', kpis => {
    $('kpiTotal').textContent = kpis.total_stops ?? '--';
    $('kpiUnassigned').textContent = kpis.unassigned ?? '--';
    $('kpiRoutes').textContent = kpis.routes_total ?? '--';
    $('kpiTrucks').textContent = kpis.trucks_out ?? '--';
  });

  // Expose focus method for keyboard shortcut
  on('focus-search', () => searchEl.focus());
}
