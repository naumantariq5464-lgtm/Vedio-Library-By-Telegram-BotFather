/* ═══════════════════════════════════════════════════════════
   VIDEOVAULT - App Logic
   ═══════════════════════════════════════════════════════════ */

const API_BASE = 'http://127.0.0.1:8000';
let allVideos = [];
let authToken = localStorage.getItem('vv_token') || null;
let currentPage = 'library';
let deleteVideoId = null;

// ─── UTILITIES ───────────────────────────────────────────────
function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function formatDuration(seconds) {
  if (!seconds || seconds === 0) return '';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function showToast(message, type = 'info') {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.className = `toast show ${type}`;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => { toast.className = 'toast'; }, 3500);
}

function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById(`page-${name}`).classList.add('active');
  currentPage = name;
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ─── SMOOTH SCROLL FOR NAV LINK ───────────────────────────────
document.getElementById('nav-videos-link').addEventListener('click', (e) => {
  e.preventDefault();
  if (currentPage !== 'library') {
    const videoEl = document.getElementById('main-video');
    if (videoEl) { videoEl.pause(); videoEl.src = ''; }
    showPage('library');
    setTimeout(() => {
      document.getElementById('videos-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  } else {
    document.getElementById('videos-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
});

const heroOrbEl = document.querySelector('.hero-orb');
if (heroOrbEl) {
  heroOrbEl.addEventListener('click', () => {
    document.getElementById('videos-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

// ─── LOAD PUBLIC VIDEOS ────────────────────────────────────────
async function loadPublicVideos() {
  try {
    const res = await fetch(`${API_BASE}/api/videos`);
    if (!res.ok) throw new Error('Failed');
    allVideos = await res.json();
    renderVideoGrid(allVideos);
    document.getElementById('stat-count').textContent = allVideos.length;
    document.getElementById('video-count-badge').textContent = `${allVideos.length} video${allVideos.length !== 1 ? 's' : ''}`;
  } catch (err) {
    document.getElementById('loading-grid').style.display = 'none';
    document.getElementById('empty-state').style.display = 'block';
    document.getElementById('video-count-badge').textContent = 'Error loading';
    showToast('Could not connect to backend', 'error');
  }
}

// ─── RENDER VIDEO GRID ────────────────────────────────────────
function renderVideoGrid(videos) {
  const grid = document.getElementById('video-grid');
  const loadingGrid = document.getElementById('loading-grid');
  const emptyState = document.getElementById('empty-state');
  const noResults = document.getElementById('no-results-state');

  loadingGrid.style.display = 'none';
  noResults.style.display = 'none';

  if (videos.length === 0) {
    const searchVal = document.getElementById('search-input').value.trim();
    if (searchVal) {
      grid.style.display = 'none';
      noResults.style.display = 'block';
      emptyState.style.display = 'none';
    } else {
      grid.style.display = 'none';
      emptyState.style.display = 'block';
    }
    return;
  }

  emptyState.style.display = 'none';
  grid.style.display = 'grid';
  grid.innerHTML = '';

  videos.forEach((video, idx) => {
    const card = document.createElement('div');
    card.className = 'video-card';
    card.style.animationDelay = `${idx * 60}ms`;
    const dur = formatDuration(video.duration);
    const streamUrl = `${API_BASE}/api/videos/${video.id}/stream`;

    card.innerHTML = `
      <div class="card-thumb" id="thumb-${video.id}">
        <video class="card-thumb-video" preload="metadata" muted playsinline loop>
          <source src="${streamUrl}#t=1" type="video/mp4">
        </video>
        <div class="card-thumb-gradient"></div>
        <div class="card-play-btn">
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
        </div>
        ${dur ? `<div class="card-duration">${dur}</div>` : ''}
      </div>
      <div class="card-body">
        <div class="card-title">${escapeHtml(video.title)}</div>
        <div class="card-meta">
          <span class="card-badge">HD</span>
          <span class="card-size">${formatBytes(video.file_size)}</span>
          <span class="card-date">${formatDate(video.created_at)}</span>
        </div>
      </div>
    `;

    const thumbVid = card.querySelector('.card-thumb-video');
    if (thumbVid) {
      // Seek to 1s once metadata loads so the real video frame shows immediately
      thumbVid.addEventListener('loadedmetadata', () => {
        try {
          if (thumbVid.currentTime === 0) {
            thumbVid.currentTime = Math.min(1, (thumbVid.duration || 1) * 0.1 || 0.5);
          }
        } catch (_) {}
      });

      // Hover to preview video
      card.addEventListener('mouseenter', () => {
        thumbVid.play().catch(() => {});
      });
      card.addEventListener('mouseleave', () => {
        thumbVid.pause();
        try {
          thumbVid.currentTime = Math.min(1, (thumbVid.duration || 1) * 0.1 || 0.5);
        } catch (_) {}
      });
    }

    card.addEventListener('click', () => {
      if (thumbVid) thumbVid.pause();
      openPlayer(video);
    });

    grid.appendChild(card);
  });
}

// ─── SEARCH ──────────────────────────────────────────────────
document.getElementById('search-input').addEventListener('input', function() {
  const q = this.value.trim().toLowerCase();
  document.getElementById('search-clear').style.display = q ? 'block' : 'none';
  if (!q) { renderVideoGrid(allVideos); return; }
  renderVideoGrid(allVideos.filter(v => v.title.toLowerCase().includes(q)));
});

document.getElementById('search-clear').addEventListener('click', () => {
  document.getElementById('search-input').value = '';
  document.getElementById('search-clear').style.display = 'none';
  renderVideoGrid(allVideos);
});

// ─── VIDEO PLAYER + AI CHAT ──────────────────────────────────
let _currentVideoId = null;

function openPlayer(video) {
  document.getElementById('player-title').textContent = video.title;
  document.getElementById('player-size').textContent = formatBytes(video.file_size);
  document.getElementById('player-date').textContent = formatDate(video.created_at);
  const videoEl = document.getElementById('main-video');
  videoEl.src = `${API_BASE}/api/videos/${video.id}/stream`;

  // Reset AI chat panel for this video
  _currentVideoId = video.id;
  resetAiChat();

  // Background prepare Gemini AI cache so queries respond instantly
  fetch(`${API_BASE}/api/videos/${video.id}/chat/prepare`, { method: 'POST' }).catch(() => {});

  showPage('player');
}

document.getElementById('back-btn').addEventListener('click', () => {
  const videoEl = document.getElementById('main-video');
  videoEl.pause();
  videoEl.src = '';
  _currentVideoId = null;
  showPage('library');
});

// ─── AI CHAT PANEL ───────────────────────────────────────────
function resetAiChat() {
  const msgs = document.getElementById('ai-chat-messages');
  msgs.innerHTML = `
    <div class="ai-chat-welcome">
      <div class="ai-welcome-icon">🤖</div>
      <p>Hello! I've analyzed this video and I'm ready to answer your questions. Ask me anything!</p>
    </div>`;
  // Re-show chips
  document.getElementById('ai-chat-chips').style.display = 'flex';
  // Un-collapse
  const body = document.getElementById('ai-chat-body');
  const toggle = document.getElementById('ai-chat-toggle');
  body.classList.remove('collapsed');
  toggle.classList.remove('collapsed');
}

// Toggle collapse
document.getElementById('ai-chat-toggle').addEventListener('click', () => {
  const body = document.getElementById('ai-chat-body');
  const toggle = document.getElementById('ai-chat-toggle');
  body.classList.toggle('collapsed');
  toggle.classList.toggle('collapsed');
});

// Quick suggestion chips
document.querySelectorAll('.ai-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    const q = chip.dataset.q;
    if (q) sendAiQuestion(q);
  });
});

// Send on Enter key
document.getElementById('ai-chat-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendAiQuestion();
  }
});

// Send button click
document.getElementById('ai-chat-send').addEventListener('click', () => sendAiQuestion());

function appendUserMsg(text) {
  const msgs = document.getElementById('ai-chat-messages');
  // Remove welcome message on first question
  const welcome = msgs.querySelector('.ai-chat-welcome');
  if (welcome) welcome.remove();

  const el = document.createElement('div');
  el.className = 'ai-msg-user';
  el.textContent = text;
  msgs.appendChild(el);
  msgs.scrollTop = msgs.scrollHeight;
}

let _typingStatusTimer = null;

function showTyping(statusText) {
  const msgs = document.getElementById('ai-chat-messages');
  const el = document.createElement('div');
  el.className = 'ai-typing';
  el.id = 'ai-typing-indicator';
  el.innerHTML = `
    <div class="ai-msg-ai-avatar">🤖</div>
    <div class="ai-typing-dots">
      <span></span><span></span><span></span>
    </div>
    <span id="ai-typing-status" style="color:var(--text-muted);font-size:12px;margin-left:6px;font-style:italic">${statusText || 'Gemini is thinking...'}</span>`;
  msgs.appendChild(el);
  msgs.scrollTop = msgs.scrollHeight;
}

function updateTypingStatus(text) {
  const el = document.getElementById('ai-typing-status');
  if (el) el.textContent = text;
}

function removeTyping() {
  if (_typingStatusTimer) {
    clearInterval(_typingStatusTimer);
    _typingStatusTimer = null;
  }
  const el = document.getElementById('ai-typing-indicator');
  if (el) el.remove();
}

function appendAiMsg(text) {
  const msgs = document.getElementById('ai-chat-messages');
  removeTyping();

  // Make timestamps clickable (e.g., "1:23" or "01:23")
  const formatted = text.replace(/\b(\d{1,2}:\d{2})\b/g, (ts) => {
    const parts = ts.split(':');
    const secs = parseInt(parts[0]) * 60 + parseInt(parts[1]);
    return `<a href="#" class="ai-timestamp-link" data-secs="${secs}" style="color:var(--red-light);text-decoration:underline;cursor:pointer">${ts}</a>`;
  });

  const el = document.createElement('div');
  el.className = 'ai-msg-ai';
  el.innerHTML = `
    <div class="ai-msg-ai-avatar">🤖</div>
    <div class="ai-msg-ai-text">${formatted}</div>`;
  msgs.appendChild(el);
  msgs.scrollTop = msgs.scrollHeight;

  // Attach timestamp seek listeners
  el.querySelectorAll('.ai-timestamp-link').forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const secs = parseFloat(link.dataset.secs);
      const videoEl = document.getElementById('main-video');
      if (videoEl && !isNaN(secs)) {
        videoEl.currentTime = secs;
        videoEl.play().catch(() => {});
      }
    });
  });
}

async function sendAiQuestion(questionOverride) {
  if (!_currentVideoId) return;

  const input = document.getElementById('ai-chat-input');
  const sendBtn = document.getElementById('ai-chat-send');
  const question = questionOverride || input.value.trim();
  if (!question) return;

  // Hide chips after first question
  document.getElementById('ai-chat-chips').style.display = 'none';

  input.value = '';
  sendBtn.disabled = true;

  appendUserMsg(question);
  showTyping('Analyzing video with Gemini AI...');

  // If first time download is needed, show progress stages
  let secondsElapsed = 0;
  _typingStatusTimer = setInterval(() => {
    secondsElapsed += 3;
    if (secondsElapsed === 3) {
      updateTypingStatus('Analyzing video frames & audio...');
    } else if (secondsElapsed === 9) {
      updateTypingStatus('Reading scenes & timestamps...');
    } else if (secondsElapsed === 18) {
      updateTypingStatus('Preparing video analysis (first-time caching)...');
    } else if (secondsElapsed === 35) {
      updateTypingStatus('Processing video stream with Gemini...');
    }
  }, 3000);

  try {
    const res = await fetch(`${API_BASE}/api/videos/${_currentVideoId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question })
    });

    const data = await res.json();

    if (!res.ok) {
      appendAiMsg(`⚠️ ${data.detail || 'Something went wrong. Please try again.'}`);
    } else {
      appendAiMsg(data.answer);
    }
  } catch (err) {
    removeTyping();
    appendAiMsg('⚠️ Could not connect to the AI service. Make sure the backend is running.');
  } finally {
    removeTyping();
    sendBtn.disabled = false;
    input.focus();
  }
}

// ─── NAVBAR ──────────────────────────────────────────────────
document.getElementById('nav-logo-btn').addEventListener('click', (e) => {
  e.preventDefault();
  const videoEl = document.getElementById('main-video');
  if (videoEl) { videoEl.pause(); videoEl.src = ''; }
  showPage('library');
});

// ─── HIDDEN FOOTER ADMIN TRIGGER (1 click on copyright) ─────────────
document.getElementById('footer-admin-trigger').addEventListener('click', () => {
  showPage('admin');
  if (authToken) {
    showDashboard();
  } else {
    document.getElementById('admin-login-panel').style.display = 'flex';
    document.getElementById('admin-dashboard').style.display = 'none';
  }
});

document.getElementById('admin-back-home').addEventListener('click', () => showPage('library'));
document.getElementById('dash-home-btn').addEventListener('click', () => showPage('library'));

// ─── ADMIN LOGIN ─────────────────────────────────────────────
document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value.trim();
  const alertBox = document.getElementById('login-alert');
  const btn = document.getElementById('login-btn');
  const spinner = document.getElementById('login-spinner');
  const btnText = document.getElementById('login-btn-text');

  alertBox.style.display = 'none';
  btn.disabled = true;
  spinner.style.display = 'inline-block';
  btnText.style.display = 'none';

  try {
    const body = `username=${encodeURIComponent(email)}&password=${encodeURIComponent(password)}`;
    const res = await fetch(`${API_BASE}/api/admin/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Login failed');
    authToken = data.access_token;
    localStorage.setItem('vv_token', authToken);
    showToast('Logged in successfully!', 'success');
    showDashboard();
  } catch (err) {
    alertBox.textContent = err.message || 'Invalid email or password';
    alertBox.style.display = 'block';
    alertBox.className = 'alert';
  } finally {
    btn.disabled = false;
    spinner.style.display = 'none';
    btnText.style.display = 'inline';
  }
});

document.getElementById('toggle-pwd').addEventListener('click', () => {
  const input = document.getElementById('login-password');
  input.type = input.type === 'password' ? 'text' : 'password';
});

// ─── DASHBOARD ───────────────────────────────────────────────
function showDashboard() {
  document.getElementById('admin-login-panel').style.display = 'none';
  document.getElementById('admin-dashboard').style.display = 'block';
  loadAdminVideos();
}

document.getElementById('logout-btn').addEventListener('click', () => {
  authToken = null;
  localStorage.removeItem('vv_token');
  document.getElementById('admin-login-panel').style.display = 'flex';
  document.getElementById('admin-dashboard').style.display = 'none';
  document.getElementById('login-email').value = '';
  document.getElementById('login-password').value = '';
  showPage('library');
  showToast('Logged out', 'info');
});

// ─── ADMIN VIDEO LIST ─────────────────────────────────────────
async function loadAdminVideos() {
  const loading = document.getElementById('admin-loading');
  const tableWrapper = document.getElementById('video-table-wrapper');
  const emptyState = document.getElementById('admin-empty-state');
  loading.style.display = 'block';
  tableWrapper.style.display = 'none';
  emptyState.style.display = 'none';

  try {
    const res = await fetch(`${API_BASE}/api/videos`);
    const videos = await res.json();

    document.getElementById('admin-video-count').textContent = videos.length;
    const totalBytes = videos.reduce((sum, v) => sum + (v.file_size || 0), 0);
    document.getElementById('admin-total-size').textContent = formatBytes(totalBytes);

    loading.style.display = 'none';
    if (videos.length === 0) { emptyState.style.display = 'block'; return; }

    const tbody = document.getElementById('video-table-body');
    tbody.innerHTML = '';
    videos.forEach(video => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="table-id">#${video.id}</td>
        <td class="table-title">${escapeHtml(video.title)}</td>
        <td class="table-size">${formatBytes(video.file_size)}</td>
        <td class="table-date">${formatDate(video.created_at)}</td>
        <td class="table-actions">
          <button class="action-play" data-id="${video.id}" data-title="${escapeHtml(video.title)}" data-size="${video.file_size}" data-date="${video.created_at}">&#9654; Play</button>
          <button class="action-delete" data-id="${video.id}" data-title="${escapeHtml(video.title)}">&#128465; Delete</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
    tableWrapper.style.display = 'block';

    tbody.querySelectorAll('.action-play').forEach(btn => {
      btn.addEventListener('click', () => {
        const video = { id: btn.dataset.id, title: btn.dataset.title, file_size: parseInt(btn.dataset.size), created_at: btn.dataset.date };
        openPlayer(video);
      });
    });
    tbody.querySelectorAll('.action-delete').forEach(btn => {
      btn.addEventListener('click', () => openDeleteModal(btn.dataset.id, btn.dataset.title));
    });
  } catch (err) {
    loading.textContent = 'Failed to load videos.';
  }
}

document.getElementById('refresh-videos-btn').addEventListener('click', loadAdminVideos);

// ─── FILE UPLOAD ──────────────────────────────────────────────
const fileDropZone = document.getElementById('file-drop-zone');
const fileInput = document.getElementById('video-file');
let selectedFile = null;

fileDropZone.addEventListener('click', (e) => { if (e.target.id !== 'remove-file-btn') fileInput.click(); });
fileInput.addEventListener('change', () => handleFileSelect(fileInput.files[0]));
fileDropZone.addEventListener('dragover', (e) => { e.preventDefault(); fileDropZone.classList.add('drag-over'); });
fileDropZone.addEventListener('dragleave', () => fileDropZone.classList.remove('drag-over'));
fileDropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  fileDropZone.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) handleFileSelect(e.dataTransfer.files[0]);
});

function handleFileSelect(file) {
  if (!file) return;
  selectedFile = file;
  document.getElementById('file-drop-content').style.display = 'none';
  document.getElementById('file-selected-info').style.display = 'flex';
  document.getElementById('file-name-display').textContent = file.name;
  document.getElementById('file-size-display').textContent = formatBytes(file.size);

  const uploadAlert = document.getElementById('upload-alert');
  if (file.size > 50 * 1024 * 1024) {
    const mb = (file.size / (1024 * 1024)).toFixed(1);
    uploadAlert.textContent = `File is ${mb} MB. Telegram Bot API maximum is 50 MB. Please choose a smaller video.`;
    uploadAlert.className = 'alert';
    uploadAlert.style.display = 'block';
  } else {
    uploadAlert.style.display = 'none';
  }
  updateUploadBtn();
}

document.getElementById('remove-file-btn').addEventListener('click', (e) => {
  e.stopPropagation();
  selectedFile = null;
  fileInput.value = '';
  document.getElementById('file-drop-content').style.display = 'block';
  document.getElementById('file-selected-info').style.display = 'none';
  document.getElementById('upload-alert').style.display = 'none';
  updateUploadBtn();
});

document.getElementById('video-title').addEventListener('input', updateUploadBtn);

function updateUploadBtn() {
  const title = document.getElementById('video-title').value.trim();
  const isOverSize = selectedFile && selectedFile.size > 50 * 1024 * 1024;
  document.getElementById('upload-btn').disabled = !title || !selectedFile || isOverSize;
}

// ─── UPLOAD FORM SUBMIT — XHR with real progress ──────────────
document.getElementById('upload-form').addEventListener('submit', (e) => {
  e.preventDefault();
  if (!authToken) { showToast('Please login first', 'error'); return; }
  if (!selectedFile) { showToast('Please select a video file', 'error'); return; }

  const title = document.getElementById('video-title').value.trim();
  const uploadAlert = document.getElementById('upload-alert');
  const progressWrapper = document.getElementById('upload-progress-wrapper');
  const progressBar = document.getElementById('upload-progress-bar');
  const progressLabel = document.getElementById('upload-progress-label');
  const uploadBtn = document.getElementById('upload-btn');
  const uploadBtnText = document.getElementById('upload-btn-text');
  const uploadSpinner = document.getElementById('upload-spinner');

  uploadAlert.style.display = 'none';
  uploadBtn.disabled = true;
  uploadSpinner.style.display = 'inline-block';
  uploadBtnText.style.display = 'none';
  progressWrapper.style.display = 'block';
  progressBar.style.width = '0%';
  progressLabel.textContent = 'Sending to backend...';

  const formData = new FormData();
  formData.append('title', title);
  formData.append('file', selectedFile);

  const xhr = new XMLHttpRequest();

  // ── Real upload progress (frontend → backend) ──
  xhr.upload.addEventListener('progress', (ev) => {
    if (!ev.lengthComputable) return;
    const pct = Math.round((ev.loaded / ev.total) * 60); // browser→backend = first 60%
    progressBar.style.width = pct + '%';
    progressLabel.textContent = pct < 60
      ? `Sending... ${pct}%`
      : 'Uploading to Telegram — please wait...';
  });

  xhr.upload.addEventListener('load', () => {
    // File reached backend; now Telegram is processing — animate 60→90%
    let p = 60;
    const iv = setInterval(() => {
      if (p < 90) { p += 1; progressBar.style.width = p + '%'; }
      else clearInterval(iv);
    }, 800);
    xhr._telegramInterval = iv;
  });

  xhr.addEventListener('load', () => {
    clearInterval(xhr._telegramInterval);

    const reset = () => {
      uploadSpinner.style.display = 'none';
      uploadBtnText.style.display = 'inline';
      uploadBtn.disabled = true;
    };

    if (xhr.status === 401) {
      authToken = null; localStorage.removeItem('vv_token');
      progressWrapper.style.display = 'none';
      uploadAlert.textContent = 'Session expired. Please login again.';
      uploadAlert.className = 'alert';
      uploadAlert.style.display = 'block';
      reset();
      return;
    }

    let data;
    try { data = JSON.parse(xhr.responseText); } catch (_) { data = {}; }

    if (xhr.status >= 200 && xhr.status < 300) {
      progressBar.style.width = '100%';
      progressLabel.textContent = 'Upload complete!';
      setTimeout(() => {
        progressWrapper.style.display = 'none';
        reset();
        document.getElementById('video-title').value = '';
        selectedFile = null;
        fileInput.value = '';
        document.getElementById('file-drop-content').style.display = 'block';
        document.getElementById('file-selected-info').style.display = 'none';
        uploadAlert.textContent = `"${data.title}" uploaded successfully! (ID: ${data.id})`;
        uploadAlert.className = 'alert success';
        uploadAlert.style.display = 'block';
        showToast('Video uploaded successfully!', 'success');
        loadAdminVideos();
        loadPublicVideos();
      }, 800);
    } else {
      progressWrapper.style.display = 'none';
      uploadAlert.textContent = data.detail || 'Upload failed. Please try again.';
      uploadAlert.className = 'alert';
      uploadAlert.style.display = 'block';
      uploadBtn.disabled = false;
      reset();
    }
  });

  xhr.addEventListener('error', () => {
    clearInterval(xhr._telegramInterval);
    progressWrapper.style.display = 'none';
    uploadAlert.textContent = 'Network error. Check your connection and try again.';
    uploadAlert.className = 'alert';
    uploadAlert.style.display = 'block';
    uploadBtn.disabled = false;
    uploadSpinner.style.display = 'none';
    uploadBtnText.style.display = 'inline';
  });

  xhr.open('POST', `${API_BASE}/api/admin/videos`);
  xhr.setRequestHeader('Authorization', `Bearer ${authToken}`);
  xhr.send(formData);
});

// ─── DELETE MODAL ─────────────────────────────────────────────
function openDeleteModal(id, title) {
  deleteVideoId = id;
  document.getElementById('modal-body-text').textContent = `Delete "${title}"? This cannot be undone.`;
  document.getElementById('delete-modal').style.display = 'flex';
}

document.getElementById('modal-cancel-btn').addEventListener('click', () => {
  document.getElementById('delete-modal').style.display = 'none';
  deleteVideoId = null;
});

document.getElementById('delete-modal').addEventListener('click', (e) => {
  if (e.target === document.getElementById('delete-modal')) {
    document.getElementById('delete-modal').style.display = 'none';
    deleteVideoId = null;
  }
});

document.getElementById('modal-confirm-btn').addEventListener('click', async () => {
  if (!deleteVideoId) return;
  const btn = document.getElementById('modal-confirm-btn');
  btn.disabled = true;
  btn.textContent = 'Deleting...';
  try {
    const res = await fetch(`${API_BASE}/api/admin/videos/${deleteVideoId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    if (!res.ok) { const d = await res.json(); throw new Error(d.detail || 'Delete failed'); }
    showToast('Video deleted successfully', 'success');
    document.getElementById('delete-modal').style.display = 'none';
    loadAdminVideos();
    loadPublicVideos();
  } catch (err) {
    showToast(err.message || 'Delete failed', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Delete';
    deleteVideoId = null;
  }
});

// ─── INIT ─────────────────────────────────────────────────────
(async function init() {
  await loadPublicVideos();
  if (authToken && currentPage === 'admin') showDashboard();
})();
