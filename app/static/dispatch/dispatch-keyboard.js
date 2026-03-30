/**
 * Keyboard shortcuts for the dispatch console.
 */
import { on, emit, getState, setState } from './dispatch-state.js';
import * as api from './dispatch-api.js';

export function init() {
  document.addEventListener('keydown', handleKeyDown);
}

function handleKeyDown(e) {
  // Skip if inside an input/select/textarea
  const tag = e.target.tagName;
  if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') {
    if (e.key === 'Escape') {
      e.target.blur();
    }
    return;
  }

  const state = getState();

  switch (e.key) {
    case '?':
      document.getElementById('shortcutsOverlay').classList.toggle('open');
      break;

    case '/':
      e.preventDefault();
      emit('focus-search', {});
      break;

    case 'n':
      if (!e.ctrlKey && !e.metaKey) {
        document.getElementById('btnNewRoute').click();
      }
      break;

    case 'Escape':
      // Close detail panel first, then shortcuts overlay, then deselect
      if (document.getElementById('shortcutsOverlay').classList.contains('open')) {
        document.getElementById('shortcutsOverlay').classList.remove('open');
      } else if (document.getElementById('settingsBackdrop').classList.contains('open')) {
        document.getElementById('settingsBackdrop').classList.remove('open');
      } else if (state.detailOpen) {
        emit('detail-close', {});
      } else {
        setState({ selectedStopId: null, selectedStopIds: new Set(), selectedRouteId: null });
        emit('selection-changed', {});
      }
      break;

    case 'ArrowDown':
      e.preventDefault();
      navigateStops(1);
      break;

    case 'ArrowUp':
      e.preventDefault();
      navigateStops(-1);
      break;

    case 'Enter':
      if (state.selectedStopId) {
        emit('detail-open', state.selectedStopId);
      }
      break;

    default:
      // 1-9: quick assign to route
      if (/^[1-9]$/.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const routeIdx = parseInt(e.key) - 1;
        quickAssignToRoute(routeIdx);
      }

      // Ctrl+P: print manifest
      if (e.key === 'p' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        if (state.selectedStopId) {
          document.dispatchEvent(new CustomEvent('dispatch:print-manifest', { detail: state.selectedStopId }));
        }
      }
      break;
  }
}

function navigateStops(direction) {
  const state = getState();
  const stops = state.stops;
  if (!stops.length) return;

  const currentId = state.selectedStopId;
  const currentIdx = stops.findIndex(s => String(s.id) === currentId);
  let nextIdx;

  if (currentIdx === -1) {
    nextIdx = direction > 0 ? 0 : stops.length - 1;
  } else {
    nextIdx = currentIdx + direction;
    if (nextIdx < 0) nextIdx = stops.length - 1;
    if (nextIdx >= stops.length) nextIdx = 0;
  }

  const nextStop = stops[nextIdx];
  if (nextStop) {
    const soId = String(nextStop.id);
    setState({ selectedStopId: soId, selectedStopIds: new Set([soId]) });
    emit('selection-changed', { soId });
    emit('stop-selected', soId);

    // Scroll the stop into view in the route panel
    const el = document.querySelector(`.stop-item[data-so-id="${soId}"]`);
    if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
}

async function quickAssignToRoute(routeIdx) {
  const state = getState();
  const route = state.routes[routeIdx];
  if (!route) return;

  const selected = state.selectedStopIds.size > 0
    ? Array.from(state.selectedStopIds)
    : state.selectedStopId ? [state.selectedStopId] : [];

  if (!selected.length) return;

  const stopsToAdd = selected.map(soId => {
    const stop = state.stops.find(s => String(s.id) === soId);
    return { so_id: soId, shipment_num: stop?.shipment_num };
  });

  try {
    await api.addStopsToRoute(route.id, stopsToAdd);
    emit('routes-reload', {});
  } catch (err) {
    console.error('Quick assign failed:', err);
  }
}
