const API_KEY = localStorage.getItem('freenvr_api_key') || promptApiKey();

function promptApiKey() {
  const key = prompt('freeNVR API-Key eingeben:') || 'changeme';
  localStorage.setItem('freenvr_api_key', key);
  return key;
}

const headers = { 'X-API-Key': API_KEY, 'Content-Type': 'application/json' };

async function api(path, opts = {}) {
  const res = await fetch('/api' + path, { headers, ...opts });
  if (!res.ok) throw new Error(await res.text());
  if (res.status === 204) return null;
  return res.json();
}

// ─── Navigation ────────────────────────────────────────────────────────────

document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('view-' + btn.dataset.view).classList.add('active');
    if (btn.dataset.view === 'live') loadLive();
    if (btn.dataset.view === 'recordings') loadRecordings();
    if (btn.dataset.view === 'events') loadEvents();
    if (btn.dataset.view === 'cameras') loadCameraList();
  });
});

// ─── Storage Info ───────────────────────────────────────────────────────────

async function loadStorageInfo() {
  try {
    const info = await api('/recordings/storage/info');
    const gb = b => (b / 1e9).toFixed(1) + ' GB';
    document.getElementById('storage-info').textContent =
      `Speicher: ${gb(info.used_bytes)} / ${gb(info.total_bytes)} · ${info.recording_count} Aufnahmen`;
  } catch (_) {}
}

// ─── Live View ──────────────────────────────────────────────────────────────

let hlsInstances = {};

async function loadLive() {
  const cameras = await api('/cameras');
  const grid = document.getElementById('camera-grid');
  grid.innerHTML = '';

  cameras.forEach(cam => {
    const tile = document.createElement('div');
    tile.className = 'camera-tile';
    const statusClass = cam.status === 'recording' ? 'status-recording' : cam.status === 'error' ? 'status-error' : 'status-stopped';
    tile.innerHTML = `
      <div class="camera-tile-header">
        <span class="camera-tile-name">
          <span class="status-dot ${statusClass}"></span>${cam.name}
        </span>
        <span style="font-size:12px;color:var(--text-muted)">${cam.recording_mode}</span>
      </div>
      <div class="camera-video-wrap">
        <video id="video-${cam.id}" controls muted autoplay playsinline></video>
      </div>
      <div class="camera-tile-actions">
        <button class="btn btn-sm" onclick="startStream(${cam.id})">▶ Stream</button>
        <button class="btn btn-sm" onclick="stopStream(${cam.id})">■ Stop</button>
        <button class="btn btn-sm" onclick="takeSnapshot(${cam.id})">📷 Snapshot</button>
      </div>`;
    grid.appendChild(tile);
  });
}

async function startStream(camId) {
  try {
    const res = await api(`/streams/${camId}/hls/start`);
    const video = document.getElementById('video-' + camId);
    const playlistUrl = `/api/streams/${camId}/hls/live.m3u8`;

    if (Hls.isSupported()) {
      if (hlsInstances[camId]) { hlsInstances[camId].destroy(); }
      const hls = new Hls({ lowLatencyMode: true });
      hls.loadSource(playlistUrl);
      hls.attachMedia(video);
      hlsInstances[camId] = hls;
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = playlistUrl;
    }
    video.play();
  } catch (e) {
    alert('Stream-Fehler: ' + e.message);
  }
}

async function stopStream(camId) {
  if (hlsInstances[camId]) {
    hlsInstances[camId].destroy();
    delete hlsInstances[camId];
  }
  const video = document.getElementById('video-' + camId);
  if (video) { video.src = ''; }
  await api(`/streams/${camId}/hls/stop`).catch(() => {});
}

async function takeSnapshot(camId) {
  const url = `/api/streams/${camId}/snapshot`;
  window.open(url + '?X-API-Key=' + API_KEY, '_blank');
}

// ─── Recordings ─────────────────────────────────────────────────────────────

async function loadRecordings() {
  await _populateCameraFilter('rec-camera-filter');
  const camId = document.getElementById('rec-camera-filter').value;
  const date = document.getElementById('rec-date-filter').value;

  let qs = '?limit=100';
  if (camId) qs += `&camera_id=${camId}`;
  if (date) {
    qs += `&start=${date}T00:00:00&end=${date}T23:59:59`;
  }

  const recs = await api('/recordings' + qs);
  const el = document.getElementById('recordings-list');
  el.innerHTML = '';

  if (!recs.length) {
    el.innerHTML = '<p style="color:var(--text-muted);padding:20px">Keine Aufnahmen gefunden</p>';
    return;
  }

  recs.forEach(r => {
    const start = new Date(r.start_time).toLocaleString('de-DE');
    const end = r.end_time ? new Date(r.end_time).toLocaleString('de-DE') : 'läuft...';
    const size = r.size_bytes ? (r.size_bytes / 1e6).toFixed(1) + ' MB' : '-';
    const item = document.createElement('div');
    item.className = 'list-item';
    item.innerHTML = `
      <div class="list-item-info">
        <div class="list-item-title">${r.camera_name}</div>
        <div class="list-item-meta">${start} → ${end} · ${size}${r.has_motion ? ' · <span style="color:var(--warning)">Bewegung</span>' : ''}</div>
      </div>
      <div class="list-item-actions">
        <a href="/api/recordings/${r.id}/download" class="btn btn-sm" download>⬇ Download</a>
        <button class="btn btn-sm btn-danger" onclick="deleteRecording(${r.id}, this)">✕</button>
      </div>`;
    el.appendChild(item);
  });
}

async function deleteRecording(id, btn) {
  if (!confirm('Aufnahme löschen?')) return;
  await api(`/recordings/${id}`, { method: 'DELETE' });
  btn.closest('.list-item').remove();
}

// ─── Events ─────────────────────────────────────────────────────────────────

async function loadEvents() {
  await _populateCameraFilter('evt-camera-filter');
  const camId = document.getElementById('evt-camera-filter').value;

  let qs = '?limit=200';
  if (camId) qs += `&camera_id=${camId}`;

  const evts = await api('/events' + qs);
  const el = document.getElementById('events-list');
  el.innerHTML = '';

  if (!evts.length) {
    el.innerHTML = '<p style="color:var(--text-muted);padding:20px">Keine Ereignisse</p>';
    return;
  }

  evts.forEach(e => {
    const ts = new Date(e.timestamp).toLocaleString('de-DE');
    const item = document.createElement('div');
    item.className = 'list-item';
    item.innerHTML = `
      <div class="list-item-info">
        <div class="list-item-title">${e.camera_name}</div>
        <div class="list-item-meta">${ts} · <strong>${e.event_type}</strong></div>
      </div>`;
    el.appendChild(item);
  });
}

// ─── Camera Management ───────────────────────────────────────────────────────

async function loadCameraList() {
  const cameras = await api('/cameras');
  const el = document.getElementById('cameras-list');
  el.innerHTML = '';

  cameras.forEach(cam => {
    const statusClass = cam.status === 'recording' ? 'status-recording' : 'status-stopped';
    const card = document.createElement('div');
    card.className = 'camera-card';
    card.innerHTML = `
      <div>
        <span class="status-dot ${statusClass}"></span>
      </div>
      <div class="camera-card-info">
        <div class="camera-card-name">${cam.name}</div>
        <div class="camera-card-url">${cam.rtsp_url}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px">
          Modus: ${cam.recording_mode} · ${cam.enabled ? 'Aktiv' : 'Inaktiv'}
        </div>
      </div>
      <div class="camera-card-actions">
        <button class="btn btn-sm" onclick="editCamera(${cam.id})">Bearbeiten</button>
        <button class="btn btn-sm btn-danger" onclick="deleteCamera(${cam.id})">Löschen</button>
      </div>`;
    el.appendChild(card);
  });
}

async function deleteCamera(id) {
  if (!confirm('Kamera wirklich löschen?')) return;
  await api(`/cameras/${id}`, { method: 'DELETE' });
  loadCameraList();
}

async function editCamera(id) {
  const cam = await api(`/cameras/${id}`);
  document.getElementById('modal-title').textContent = 'Kamera bearbeiten';
  document.getElementById('cam-id').value = cam.id;
  document.getElementById('cam-name').value = cam.name;
  document.getElementById('cam-rtsp').value = cam.rtsp_url;
  document.getElementById('cam-sub').value = cam.substream_url || '';
  document.getElementById('cam-user').value = cam.username || '';
  document.getElementById('cam-pass').value = '';
  document.getElementById('cam-mode').value = cam.recording_mode;
  document.getElementById('cam-enabled').checked = cam.enabled;
  document.getElementById('modal').classList.remove('hidden');
}

function showAddCamera() {
  document.getElementById('modal-title').textContent = 'Kamera hinzufügen';
  document.getElementById('camera-form').reset();
  document.getElementById('cam-id').value = '';
  document.getElementById('cam-enabled').checked = true;
  document.getElementById('modal').classList.remove('hidden');
}

function closeModal() {
  document.getElementById('modal').classList.add('hidden');
}

document.getElementById('camera-form').addEventListener('submit', async e => {
  e.preventDefault();
  const id = document.getElementById('cam-id').value;
  const payload = {
    name: document.getElementById('cam-name').value,
    rtsp_url: document.getElementById('cam-rtsp').value,
    substream_url: document.getElementById('cam-sub').value || null,
    username: document.getElementById('cam-user').value || null,
    password: document.getElementById('cam-pass').value || null,
    recording_mode: document.getElementById('cam-mode').value,
    enabled: document.getElementById('cam-enabled').checked,
  };

  try {
    if (id) {
      await api(`/cameras/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
    } else {
      await api('/cameras', { method: 'POST', body: JSON.stringify(payload) });
    }
    closeModal();
    loadCameraList();
  } catch (err) {
    alert('Fehler: ' + err.message);
  }
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function _populateCameraFilter(selectId) {
  const sel = document.getElementById(selectId);
  const existing = [...sel.options].map(o => o.value);
  if (existing.length > 1) return;
  const cameras = await api('/cameras');
  cameras.forEach(cam => {
    const opt = document.createElement('option');
    opt.value = cam.id;
    opt.textContent = cam.name;
    sel.appendChild(opt);
  });
}

// ─── Init ────────────────────────────────────────────────────────────────────

(async () => {
  await loadStorageInfo();
  await loadLive();
  setInterval(loadStorageInfo, 60000);
})();
