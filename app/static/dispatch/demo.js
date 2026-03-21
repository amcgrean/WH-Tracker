const API_BASE = (window.DISPATCH_API_BASE || '').trim() || '';
const DEFAULTS = {
  refreshSec: 20,
  denseRows: false,
  rememberBranch: true,
  colors: { K: '#2ca02c', S: '#1f77b4', B: '#ff7f0e', CM: '#d62728' }
};
const SKEY = 'dispatch_settings_v1';

function loadSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(SKEY) || '{}');
    return {
      refreshSec: Math.max(0, Number(saved.refreshSec ?? DEFAULTS.refreshSec) || DEFAULTS.refreshSec),
      denseRows: !!saved.denseRows,
      rememberBranch: saved.rememberBranch ?? DEFAULTS.rememberBranch,
      colors: { ...DEFAULTS.colors, ...(saved.colors || {}) }
    };
  } catch (_error) {
    return JSON.parse(JSON.stringify(DEFAULTS));
  }
}

(function () {
  const map = L.map('map').setView([41.5868, -93.6250], 10);
  const street = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap' });
  const sat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19, attribution: '&copy; Esri, Maxar' });
  street.addTo(map);
  let currentBase = 'street';
  let layerGroup = L.layerGroup().addTo(map);
  let filtered = [];
  let selection = new Set();
  let sortKey = 'expected_date';
  let sortDir = 'asc';
  let timerId = null;
  let lastUpdate = 0;

  const statusEl = document.getElementById('status');
  const branchEl = document.getElementById('branch');
  const startEl = document.getElementById('startDate');
  const endEl = document.getElementById('endDate');
  const showKEl = document.getElementById('showK');
  const showSEl = document.getElementById('showS');
  const showBEl = document.getElementById('showB');
  const showCMEl = document.getElementById('showCM');
  const refreshEl = document.getElementById('refresh');
  const loadBtn = document.getElementById('loadBtn');
  const baseEl = document.getElementById('basemap');
  const tbody = document.querySelector('#grid tbody');
  const searchEl = document.getElementById('search');
  const manifestBtn = document.getElementById('manifestBtn');
  const app = document.getElementById('app');
  const divider = document.getElementById('divider');
  const gear = document.getElementById('gear');
  const backdrop = document.getElementById('modalBackdrop');
  const prefBranch = document.getElementById('prefBranch');
  const prefBasemap = document.getElementById('prefBasemap');
  const prefRefresh = document.getElementById('prefRefresh');
  const refreshSecInput = document.getElementById('refreshSec');
  const denseRowsInput = document.getElementById('denseRows');
  const rememberBranchInput = document.getElementById('rememberBranch');
  const colorKInput = document.getElementById('colorK');
  const colorSInput = document.getElementById('colorS');
  const colorBInput = document.getElementById('colorB');
  const colorCMInput = document.getElementById('colorCM');
  const saveSettingsBtn = document.getElementById('saveSettings');
  const cancelSettingsBtn = document.getElementById('cancelSettings');
  const detailPanel = document.getElementById('detailPanel');
  const detailClose = document.getElementById('detailClose');
  const detailTitle = document.getElementById('detailTitle');
  const detailSubtitle = document.getElementById('detailSubtitle');
  const detailMeta = document.getElementById('detailMeta');
  const detailLines = document.getElementById('detailLines');

  function fmt(value, digits = 0) {
    if (value == null || Number.isNaN(Number(value))) return '';
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });
  }

  function refreshSeconds() {
    const raw = Number(refreshEl.value);
    if (Number.isFinite(raw) && raw >= 0) return raw;
    return loadSettings().refreshSec;
  }

  function gpsMeta(row) {
    const gpsStatus = String(row.gps_status || '').toLowerCase();
    const gpsVerified = row.gps_verified === true || gpsStatus === 'exact' || gpsStatus === 'verified';
    let gpsLabel = 'Unverified GPS';
    if (gpsVerified) gpsLabel = 'Verified GPS';
    else if (gpsStatus === 'csv_unverified') gpsLabel = 'Unverified GPS (CSV)';
    else if (gpsStatus) gpsLabel = `Unverified GPS (${gpsStatus})`;
    return { gpsStatus, gpsVerified, gpsLabel };
  }

  function openModal() { backdrop.style.display = 'flex'; }
  function closeModal() { backdrop.style.display = 'none'; }
  function openDetails() { detailPanel.classList.add('open'); }
  function closeDetails() { detailPanel.classList.remove('open'); }

  function applyToolbarColors() {
    const settings = loadSettings();
    document.getElementById('swK').style.background = settings.colors.K;
    document.getElementById('swS').style.background = settings.colors.S;
    document.getElementById('swB').style.background = settings.colors.B;
    document.getElementById('swCM').style.background = settings.colors.CM;
  }

  function selectedVehicleBranches() {
    const branch = (branchEl.value || '').toUpperCase();
    if (!branch) return [];
    if (branch === 'GRIMES_AREA' || branch === 'GRIMES') return ['20GR', '25BW'];
    return [branch];
  }

  function stopColorFor(row) {
    const { colors } = loadSettings();
    const typeUp = String(row.so_type || row.type || row.doc_kind || '').toUpperCase();
    if (typeUp === 'CM' || typeUp.includes('CREDIT')) return colors.CM;
    const statusUp = String(row.so_status || '').toUpperCase();
    if (statusUp.startsWith('K')) return colors.K;
    if (statusUp.startsWith('B')) return colors.B;
    if (statusUp.startsWith('S')) return colors.S;
    return colors.S;
  }

  function passesCheckboxes(row) {
    const kind = row.doc_kind || row.type;
    if (kind === 'credit' || String(row.so_type || '').toUpperCase() === 'CM') return showCMEl.checked;
    const status = String(row.so_status || '').toUpperCase();
    if (status === 'K') return showKEl.checked;
    if (status === 'S') return showSEl.checked;
    if (status === 'B' || status === '') return showBEl.checked;
    return showKEl.checked || showSEl.checked || showBEl.checked;
  }

  function applySearch(rows) {
    const query = searchEl.value.trim().toLowerCase();
    if (!query) return rows;
    return rows.filter((row) => {
      const fields = [row.id, row.shipto_name, row.address, row.route_id, row.driver, row.branch].map((value) => (value || '').toString().toLowerCase());
      return fields.some((field) => field.includes(query));
    });
  }

  function sortRows(rows) {
    const dir = sortDir === 'asc' ? 1 : -1;
    return rows.slice().sort((a, b) => {
      const va = a[sortKey] ?? '';
      const vb = b[sortKey] ?? '';
      if (va < vb) return -1 * dir;
      if (va > vb) return 1 * dir;
      return 0;
    });
  }

  function updateManifestButton() {
    manifestBtn.disabled = !(selection.size >= 1 && selection.size <= 10);
    manifestBtn.textContent = `Create Manifest PDF (${selection.size}/10)`;
  }

  function setRowSelected(id, isSelected) {
    const tr = tbody.querySelector(`tr[data-id="${id}"]`);
    if (!tr) return;
    tr.classList.toggle('selected', isSelected);
    const checkbox = tr.querySelector('input[type="checkbox"]');
    if (checkbox) checkbox.checked = isSelected;
  }

  function toggleSelectionById(id) {
    if (selection.has(id)) selection.delete(id);
    else if (selection.size < 10) selection.add(id);
    setRowSelected(id, selection.has(id));
    updateManifestButton();
  }

  function showVehicleDetails(vehicle) {
    detailTitle.textContent = `Truck ${vehicle.name || vehicle.id || ''}`.trim();
    detailSubtitle.textContent = [
      vehicle.branch ? `Branch ${vehicle.branch}` : '',
      vehicle.lat != null && vehicle.lon != null ? `${Number(vehicle.lat).toFixed(5)}, ${Number(vehicle.lon).toFixed(5)}` : ''
    ].filter(Boolean).join(' • ');
    detailMeta.innerHTML = [
      '<span class="pill-meta">Truck</span>',
      vehicle.branch ? `<span class="pill-meta">${vehicle.branch}</span>` : '',
      vehicle.speed != null ? `<span class="pill-meta">Speed ${fmt(vehicle.speed)} mph</span>` : '',
      vehicle.heading != null ? `<span class="pill-meta">Heading ${fmt(vehicle.heading)}&deg;</span>` : '',
      vehicle.located_at ? `<span class="pill-meta">Seen ${new Date(vehicle.located_at).toLocaleString()}</span>` : '',
      Array.isArray(vehicle.tags) && vehicle.tags.length ? `<span class="pill-meta">${vehicle.tags.join(', ')}</span>` : ''
    ].filter(Boolean).join(' ');
    detailLines.innerHTML = '<tr><td colspan="7" class="muted">Live Samsara vehicle details are shown above.</td></tr>';
    openDetails();
  }

  function renderMarkers(rows) {
    layerGroup.clearLayers();
    const latlngs = [];
    rows.forEach((row) => {
      if (row.lat == null || row.lon == null) return;
      const isCredit = (row.doc_kind || row.type) === 'credit' || String(row.so_type || '').toUpperCase() === 'CM';
      const color = isCredit ? loadSettings().colors.CM : stopColorFor(row);
      const { gpsVerified, gpsLabel } = gpsMeta(row);
      const marker = isCredit
        ? L.circleMarker([row.lat, row.lon], { radius: gpsVerified ? 9 : 8, weight: 2, color, fill: false, dashArray: gpsVerified ? null : '5 4', opacity: gpsVerified ? 1 : 0.75 })
        : L.circleMarker([row.lat, row.lon], { radius: gpsVerified ? 9 : 8, weight: 2, color: gpsVerified ? '#ffffff' : '#334155', fillColor: color, fillOpacity: gpsVerified ? 0.85 : 0.55, dashArray: gpsVerified ? null : '5 4', opacity: gpsVerified ? 1 : 0.82 });
      marker.bindPopup(`<div><div><strong>${row.id}</strong> <span>${row.doc_kind ?? row.type ?? ''}</span></div><div>${row.shipto_name ?? ''}</div><div>Expected: ${row.expected_date ?? ''}</div><div>Status: ${row.so_status ?? ''} • Branch: ${row.branch ?? ''} • Route: ${row.route_id ?? ''}</div><div>Shipment #: ${row.shipment_num ?? ''} • Driver: ${row.driver ?? ''}</div><div>GPS: ${gpsLabel}</div></div>`).addTo(layerGroup);
      marker.on('click', async () => {
        toggleSelectionById(row.id);
        try { await showDetailsForRow(row); } catch (_error) {}
      });
      latlngs.push([row.lat, row.lon]);
    });
    if (latlngs.length) map.fitBounds(L.latLngBounds(latlngs).pad(0.2));
  }

  async function showDetailsForRow(row) {
    const { gpsLabel } = gpsMeta(row);
    detailTitle.textContent = `Order ${row.id}`;
    detailSubtitle.textContent = [row.shipto_name, row.address].filter(Boolean).join(' • ');
    detailMeta.innerHTML = [
      row.doc_kind ? `<span class="pill-meta">${String(row.doc_kind).toUpperCase()}</span>` : '',
      row.so_status ? `<span class="pill-meta">Status ${row.so_status}</span>` : '',
      row.branch ? `<span class="pill-meta">${row.branch}</span>` : '',
      row.route_id ? `<span class="pill-meta">Route ${row.route_id}</span>` : '',
      row.driver ? `<span class="pill-meta">Driver ${row.driver}</span>` : '',
      row.item_count != null ? `<span class="pill-meta">Items: ${fmt(row.item_count)}</span>` : '',
      row.total_weight != null ? `<span class="pill-meta">Weight: ${fmt(row.total_weight, 2)}</span>` : '',
      `<span class="pill-meta">${gpsLabel}</span>`
    ].filter(Boolean).join(' ');

    const params = new URLSearchParams();
    if (row.shipment_num) params.set('shipment_num', String(row.shipment_num));
    const res = await fetch(`${API_BASE}/api/orders/${row.id}/lines?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const lines = await res.json();
    detailLines.innerHTML = '';
    if (!Array.isArray(lines) || !lines.length) {
      detailLines.innerHTML = '<tr><td colspan="7" class="muted">No lines found.</td></tr>';
    } else {
      lines.forEach((line) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${line.line_no ?? ''}</td><td>${line.item_id ?? ''}</td><td>${line.item_description ?? ''}</td><td>${fmt(line.qty_ordered)}</td><td>${fmt(line.qty_shipped)}</td><td>${line.uom ?? ''}</td><td>${fmt(line.weight, 2)}</td>`;
        detailLines.appendChild(tr);
      });
    }
    openDetails();
  }

  function renderTable(rows) {
    tbody.innerHTML = '';
    rows.forEach((row) => {
      const { gpsVerified } = gpsMeta(row);
      const tr = document.createElement('tr');
      tr.dataset.id = row.id;
      tr.classList.toggle('selected', selection.has(row.id));
      if (!gpsVerified) tr.style.opacity = '0.88';
      tr.innerHTML = `<td style="white-space:nowrap;"><button class="btn-primary" data-act="details" aria-label="View details">Details</button><input type="checkbox" ${selection.has(row.id) ? 'checked' : ''} aria-label="select row" style="margin-left:6px;"></td><td>${row.id ?? ''}</td><td>${row.doc_kind ?? row.type ?? ''}</td><td>${row.shipto_name ?? ''}</td><td>${row.address ?? ''}${gpsVerified ? '' : ' <span class="muted">(GPS unverified)</span>'}</td><td>${row.expected_date ?? ''}</td><td>${row.so_status ?? ''}</td><td>${row.branch ?? ''}</td><td>${row.route_id ?? ''}</td><td>${row.shipment_num ?? ''}</td>`;
      tr.querySelector('button[data-act="details"]').addEventListener('click', async (event) => {
        event.stopPropagation();
        try { await showDetailsForRow(row); } catch (error) { alert(`Failed to load order details: ${error.message}`); }
      });
      tr.querySelector('input[type="checkbox"]').addEventListener('click', (event) => {
        event.stopPropagation();
        toggleSelectionById(row.id);
      });
      tr.addEventListener('click', () => toggleSelectionById(row.id));
      tbody.appendChild(tr);
    });
  }

  async function loadStops() {
    statusEl.textContent = 'loading...';
    const url = new URL(`${API_BASE}/api/stops`, window.location.origin);
    url.searchParams.set('start', startEl.value);
    url.searchParams.set('end', endEl.value);
    const branchValue = (branchEl.value || '').toUpperCase();
    if (branchValue) url.searchParams.set('branch', branchValue);

    let data = [];
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await res.json();
    } catch (_error) {
      data = [];
    }

    filtered = sortRows(applySearch(data.filter(passesCheckboxes)));
    renderMarkers(filtered);
    renderTable(filtered);
    VehiclesOverlay.setBranch(selectedVehicleBranches());
    lastUpdate = Date.now();
    statusEl.textContent = `${filtered.length} stops • updated ${new Date(lastUpdate).toLocaleTimeString()} • refresh ${refreshSeconds() === 0 ? 'off' : `${refreshSeconds()}s`}`;
    updateManifestButton();
  }

  function setTimer() {
    if (timerId) window.clearInterval(timerId);
    const refreshSec = refreshSeconds();
    if (refreshSec > 0) timerId = window.setInterval(loadStops, refreshSec * 1000);
    VehiclesOverlay.setRefreshSec(refreshSec);
  }

  async function createManifest() {
    const rows = filtered.filter((row) => selection.has(row.id));
    if (!rows.length) return;
    const enriched = await Promise.all(rows.map(async (row) => {
      const params = new URLSearchParams();
      if (row.shipment_num) params.set('shipment_num', String(row.shipment_num));
      const res = await fetch(`${API_BASE}/api/orders/${row.id}/lines?${params.toString()}`);
      const lines = res.ok ? await res.json() : [];
      return { ...row, lines };
    }));
    const response = await fetch(`${API_BASE}/api/manifest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: enriched }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    window.open(blobUrl, '_blank');
  }

  const today = new Date();
  const toISO = (value) => value.toISOString().slice(0, 10);

  function addBusinessDays(dt, days) {
    const result = new Date(dt);
    const sign = days < 0 ? -1 : 1;
    let remaining = Math.abs(days);
    while (remaining > 0) {
      result.setDate(result.getDate() + sign);
      const dow = result.getDay();
      if (dow !== 0 && dow !== 6) remaining--;
    }
    return result;
  }

  startEl.value = startEl.value || toISO(addBusinessDays(today, -7));
  endEl.value = endEl.value || toISO(addBusinessDays(today, 1));

  const savedWidth = localStorage.getItem('dispatch_sidebar_px');
  if (savedWidth) app.style.gridTemplateColumns = `${savedWidth}px 6px 1fr`;

  divider.addEventListener('mousedown', () => { document.body.style.userSelect = 'none'; });
  window.addEventListener('mousemove', (event) => {
    if (document.body.style.userSelect !== 'none') return;
    const newWidth = Math.min(820, Math.max(360, event.clientX));
    app.style.gridTemplateColumns = `${newWidth}px 6px 1fr`;
  });
  window.addEventListener('mouseup', () => {
    if (document.body.style.userSelect === 'none') {
      document.body.style.userSelect = '';
      localStorage.setItem('dispatch_sidebar_px', getComputedStyle(app).gridTemplateColumns.split(' ')[0].replace('px', ''));
    }
  });

  detailClose.addEventListener('click', closeDetails);
  gear.addEventListener('click', openModal);
  cancelSettingsBtn.addEventListener('click', closeModal);
  backdrop.addEventListener('click', (event) => { if (event.target === backdrop) closeModal(); });

  const settings = loadSettings();
  refreshSecInput.value = settings.refreshSec;
  denseRowsInput.checked = settings.denseRows;
  rememberBranchInput.checked = settings.rememberBranch;
  colorKInput.value = settings.colors.K;
  colorSInput.value = settings.colors.S;
  colorBInput.value = settings.colors.B;
  colorCMInput.value = settings.colors.CM;
  document.body.classList.toggle('dense', settings.denseRows);
  prefBranch.value = branchEl.value || '';
  prefBasemap.value = baseEl.value || 'street';
  prefRefresh.value = String(settings.refreshSec);
  refreshEl.value = String(settings.refreshSec);
  applyToolbarColors();

  saveSettingsBtn.addEventListener('click', () => {
    const next = {
      refreshSec: Math.max(0, Number(refreshSecInput.value || DEFAULTS.refreshSec)),
      denseRows: denseRowsInput.checked,
      rememberBranch: rememberBranchInput.checked,
      colors: { K: colorKInput.value, S: colorSInput.value, B: colorBInput.value, CM: colorCMInput.value }
    };
    localStorage.setItem(SKEY, JSON.stringify(next));
    document.body.classList.toggle('dense', next.denseRows);
    branchEl.value = prefBranch.value;
    baseEl.value = prefBasemap.value;
    refreshEl.value = String(Math.max(0, Number(prefRefresh.value || next.refreshSec)));
    if (baseEl.value === 'sat' && currentBase !== 'sat') {
      map.removeLayer(street);
      sat.addTo(map);
      currentBase = 'sat';
    } else if (baseEl.value === 'street' && currentBase !== 'street') {
      map.removeLayer(sat);
      street.addTo(map);
      currentBase = 'street';
    }
    applyToolbarColors();
    VehiclesOverlay.setBranch(selectedVehicleBranches());
    VehiclesOverlay.setRefreshSec(refreshSeconds());
    setTimer();
    loadStops();
    closeModal();
  });

  baseEl.addEventListener('change', () => {
    if (baseEl.value === 'sat' && currentBase !== 'sat') {
      map.removeLayer(street);
      sat.addTo(map);
      currentBase = 'sat';
    } else if (baseEl.value === 'street' && currentBase !== 'street') {
      map.removeLayer(sat);
      street.addTo(map);
      currentBase = 'street';
    }
  });

  [showKEl, showSEl, showBEl, showCMEl].forEach((checkbox) => checkbox.addEventListener('change', loadStops));
  [branchEl, startEl, endEl, refreshEl].forEach((el) => el.addEventListener('change', () => { setTimer(); loadStops(); }));
  refreshEl.addEventListener('input', setTimer);
  searchEl.addEventListener('input', loadStops);
  loadBtn.addEventListener('click', loadStops);
  manifestBtn.addEventListener('click', async () => {
    try { await createManifest(); } catch (error) { alert(`Failed to create manifest: ${error.message}`); }
  });
  document.querySelectorAll('#grid th[data-key]').forEach((th) => {
    th.addEventListener('click', () => {
      const nextKey = th.dataset.key;
      if (!nextKey || nextKey === '_sel') return;
      if (sortKey === nextKey) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
      else { sortKey = nextKey; sortDir = 'asc'; }
      loadStops();
    });
  });

  VehiclesOverlay.init({
    map,
    apiBase: API_BASE,
    refreshSec: refreshSeconds(),
    onStatus: (text) => { document.getElementById('vehicleStatus').textContent = text; },
    legend: true,
  });
  document.addEventListener('dispatch:vehicle-selected', (event) => showVehicleDetails(event.detail || {}));
  VehiclesOverlay.setBranch(selectedVehicleBranches());
  VehiclesOverlay.start();

  loadStops();
  setTimer();
})();
