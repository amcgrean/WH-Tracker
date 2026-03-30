/**
 * Detail flyout: order info, line items, customer credit, WOs, picks, actions.
 */
import { on, emit, getState, setState } from './dispatch-state.js';
import * as api from './dispatch-api.js';

let panel, grid, titleEl, subtitleEl, bodyEl;
let currentStopId = null;

const TIMELINE_STEPS = ['Ordered', 'Picked', 'Staged', 'Loaded', 'En Route', 'Delivered'];

export function init() {
  panel = document.getElementById('detailPanel');
  grid = document.getElementById('dispatchGrid');
  titleEl = document.getElementById('detailTitle');
  subtitleEl = document.getElementById('detailSubtitle');
  bodyEl = document.getElementById('detailBody');

  document.getElementById('detailClose').addEventListener('click', close);

  on('detail-open', open);
  on('stop-selected', soId => {
    if (panel.classList.contains('open')) {
      open(soId);
    }
  });
}

function open(soId) {
  currentStopId = String(soId);
  panel.classList.add('open');
  grid.classList.add('detail-open');
  setState({ detailOpen: true });
  loadDetail(currentStopId);
}

function close() {
  panel.classList.remove('open');
  grid.classList.remove('detail-open');
  setState({ detailOpen: false });
  currentStopId = null;
}

export { close };

async function loadDetail(soId) {
  const state = getState();
  const stop = state.stops.find(s => String(s.id) === soId);

  titleEl.textContent = stop ? (stop.shipto_name || soId) : `Order ${soId}`;
  subtitleEl.textContent = stop ? `SO# ${soId}${stop.address ? ' — ' + stop.address : ''}` : '';

  // Show loading state
  setSection('detailTimeline', '<div style="color:#aaa; font-size:12px; padding:8px 0;">Loading...</div>');
  setSection('detailSummary', '');
  setSection('detailLines', '');
  setSection('detailCredit', '');
  setSection('detailWorkOrders', '');
  setSection('detailPicks', '');
  setSection('detailActions', '');

  // Render what we have immediately
  if (stop) {
    renderTimeline(stop);
    renderSummary(stop);
    renderActions(stop);
  }

  // Load additional data in parallel
  const shipmentNum = stop?.shipment_num;
  const custKey = stop?.customer_name || stop?.shipto_name;

  const promises = [];

  promises.push(
    api.loadOrderLines(soId, shipmentNum)
      .then(data => renderLines(data))
      .catch(() => setSection('detailLines', sectionTitle('Line Items') + '<div style="color:#aaa;font-size:12px;">No line data available</div>'))
  );

  if (custKey) {
    promises.push(
      api.loadCustomerSummary(custKey)
        .then(data => renderCredit(data))
        .catch(() => setSection('detailCredit', sectionTitle('Customer Credit') + '<div style="color:#aaa;font-size:12px;">No credit data</div>'))
    );
  }

  promises.push(
    api.loadOrderWorkOrders(soId)
      .then(data => renderWorkOrders(data))
      .catch(() => setSection('detailWorkOrders', ''))
  );

  promises.push(
    api.loadOrderTimeline(soId)
      .then(data => renderTimelineEvents(data))
      .catch(() => {})
  );

  await Promise.allSettled(promises);
}

function renderTimeline(stop) {
  const statusMap = {
    'not_picked': 0,
    'partial': 1,
    'picked': 1,
    'staged': 2,
    'loaded': 3,
    'en_route': 4,
    'delivered': 5,
  };

  const currentStep = statusMap[stop.pick_status] || 0;

  let html = sectionTitle('Status');
  html += '<div class="timeline-stepper">';
  TIMELINE_STEPS.forEach((label, i) => {
    const cls = i < currentStep ? 'completed' : i === currentStep ? 'active' : '';
    if (i > 0) {
      html += `<div class="timeline-line${i <= currentStep ? ' completed' : ''}"></div>`;
    }
    html += `<div class="timeline-step ${cls}">
      <div class="step-dot"></div>
      <div class="step-label">${label}</div>
    </div>`;
  });
  html += '</div>';

  setSection('detailTimeline', html);
}

function renderSummary(stop) {
  let html = sectionTitle('Order Summary');
  html += '<div style="display:grid; grid-template-columns:1fr 1fr; gap:2px 12px;">';
  html += row('Value', stop.order_value ? `$${fmt(stop.order_value)}` : '--');
  html += row('Weight', stop.total_weight ? `${fmt(stop.total_weight)} lb` : '--');
  html += row('Items', stop.item_count || '--');
  html += row('Ship Via', stop.ship_via || '--');
  html += row('PO#', stop.po_number || '--');
  html += row('Salesperson', stop.salesperson || '--');
  html += row('Promise Date', stop.promise_date || '--');
  html += row('Expected', stop.expected_date || '--');
  if (stop.credit_hold) {
    html += `<div class="detail-row" style="grid-column:1/-1;"><span class="badge-sm badge-credit-hold" style="font-size:12px;">CREDIT HOLD</span></div>`;
  }
  html += '</div>';

  setSection('detailSummary', html);
}

function renderLines(data) {
  const lines = data.lines || data || [];
  if (!lines.length) {
    setSection('detailLines', sectionTitle('Line Items') + '<div style="color:#aaa;font-size:12px;">No lines</div>');
    return;
  }

  let html = sectionTitle(`Line Items (${lines.length})`);
  html += '<div style="max-height:200px;overflow-y:auto;">';
  html += '<table class="detail-table"><thead><tr>';
  html += '<th>Item</th><th>Description</th><th>Qty</th><th>Shipped</th><th>UOM</th><th>Wt</th>';
  html += '</tr></thead><tbody>';

  lines.forEach(l => {
    html += `<tr>
      <td>${esc(l.item_id || l.item || '')}</td>
      <td style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(l.description || '')}">${esc(l.description || '')}</td>
      <td>${l.qty_ordered ?? l.qty ?? '--'}</td>
      <td>${l.qty_shipped ?? '--'}</td>
      <td>${l.uom || ''}</td>
      <td>${l.weight ? fmt(l.weight) : '--'}</td>
    </tr>`;
  });

  html += '</tbody></table></div>';
  setSection('detailLines', html);
}

function renderCredit(data) {
  const summary = data.summary || data;
  if (!summary) return;

  const balance = summary.balance || 0;
  const limit = summary.credit_limit || 0;
  const available = limit - balance;
  const pct = limit > 0 ? Math.min(100, (balance / limit) * 100) : 0;
  const barColor = pct > 90 ? '#d62728' : pct > 70 ? '#ff7f0e' : '#2ca02c';

  let html = sectionTitle('Customer Credit');
  html += `<div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:4px; text-align:center; margin-bottom:6px;">
    <div><div style="font-size:16px;font-weight:700;">$${fmt(balance)}</div><div style="font-size:10px;color:#888;">Balance</div></div>
    <div><div style="font-size:16px;font-weight:700;">$${fmt(limit)}</div><div style="font-size:10px;color:#888;">Limit</div></div>
    <div><div style="font-size:16px;font-weight:700;color:${barColor};">$${fmt(available)}</div><div style="font-size:10px;color:#888;">Available</div></div>
  </div>`;
  html += `<div class="credit-bar"><div class="credit-bar-fill" style="width:${pct}%;background:${barColor};"></div></div>`;

  // Aging buckets
  if (summary.aging) {
    html += '<div style="margin-top:8px;">';
    html += '<div style="font-size:11px;font-weight:600;margin-bottom:4px;">AR Aging</div>';
    html += '<div style="display:grid; grid-template-columns:repeat(4,1fr); gap:4px; text-align:center;">';
    ['current', '30', '60', '90+'].forEach((bucket, i) => {
      const keys = ['current', 'over_30', 'over_60', 'over_90'];
      const val = summary.aging[keys[i]] || 0;
      html += `<div style="padding:4px;background:#f8f9fa;border-radius:4px;">
        <div style="font-size:13px;font-weight:600;">$${fmt(val)}</div>
        <div style="font-size:10px;color:#888;">${bucket}</div>
      </div>`;
    });
    html += '</div></div>';
  }

  setSection('detailCredit', html);
}

function renderWorkOrders(data) {
  const wos = data.work_orders || data || [];
  if (!wos.length) {
    setSection('detailWorkOrders', '');
    return;
  }

  let html = sectionTitle(`Work Orders (${wos.length})`);
  html += '<table class="detail-table"><thead><tr>';
  html += '<th>WO#</th><th>Status</th><th>Item</th><th>Qty</th><th>Dept</th>';
  html += '</tr></thead><tbody>';

  wos.forEach(wo => {
    html += `<tr>
      <td>${esc(wo.wo_id || '')}</td>
      <td>${esc(wo.status || '')}</td>
      <td>${esc(wo.item || '')}</td>
      <td>${wo.qty ?? '--'}</td>
      <td>${esc(wo.department || '')}</td>
    </tr>`;
  });

  html += '</tbody></table>';
  setSection('detailWorkOrders', html);
}

function renderTimelineEvents(data) {
  const events = data.events || data || [];
  if (!events.length) return;

  const picksHtml = events
    .filter(e => e.event_type === 'pick' || e.type === 'pick')
    .map(e => `<div style="font-size:12px;padding:2px 0;">
      <span style="color:#888;">${e.timestamp ? new Date(e.timestamp).toLocaleString() : ''}</span>
      ${esc(e.description || e.detail || '')}
    </div>`).join('');

  if (picksHtml) {
    setSection('detailPicks', sectionTitle('Pick Activity') + picksHtml);
  }
}

function renderActions(stop) {
  const soId = stop.id;
  const routes = getState().routes;

  let html = sectionTitle('Actions');
  html += '<div class="action-buttons">';

  // Working actions
  html += `<button class="action-btn primary" onclick="document.dispatchEvent(new CustomEvent('dispatch:print-manifest', {detail:'${soId}'}))">Print Manifest</button>`;

  if (routes.length) {
    html += '<select class="action-btn" id="detailAssignRoute" style="padding:5px 8px;">';
    html += '<option value="">Assign to Route...</option>';
    routes.forEach(r => {
      html += `<option value="${r.id}">${esc(r.route_name)}</option>`;
    });
    html += '</select>';
  }

  // Future Agility API actions (disabled stubs)
  html += '<button class="action-btn" disabled title="Coming: Agility API">Create Pick File</button>';
  html += '<button class="action-btn" disabled title="Coming: Agility API">Stage Shipment</button>';
  html += '<button class="action-btn" disabled title="Coming: Agility API">Mark Loaded</button>';
  html += '<button class="action-btn" disabled title="Coming: Agility API">Update Status</button>';
  html += '<button class="action-btn" disabled title="Coming: Agility API">Record POD</button>';

  html += '</div>';
  setSection('detailActions', html);

  // Bind assign-to-route dropdown
  setTimeout(() => {
    const sel = document.getElementById('detailAssignRoute');
    if (sel) {
      sel.addEventListener('change', async () => {
        const routeId = parseInt(sel.value);
        if (!routeId) return;
        try {
          await api.addStopsToRoute(routeId, [{ so_id: soId, shipment_num: stop.shipment_num }]);
          emit('routes-reload', {});
          sel.value = '';
        } catch (err) {
          console.error('Assign failed:', err);
        }
      });
    }
  }, 0);
}

// ── Helpers ──

function setSection(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

function sectionTitle(text) {
  return `<div class="detail-section-title">${text}</div>`;
}

function row(label, value) {
  return `<div class="detail-row"><span class="label">${label}</span><span class="value">${value}</span></div>`;
}

function fmt(n) {
  if (n == null) return '';
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function esc(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}
