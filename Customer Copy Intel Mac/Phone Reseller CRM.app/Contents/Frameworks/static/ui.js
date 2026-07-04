/* Shared UI utilities */

const THEME_KEY = 'crm-theme';

const UI_DESIGNS = [
  { id: 'default-dark', name: 'Glass Dark', desc: 'Frosted glass morphism (original)', colors: ['#030712', '#10b981', '#0f172a'] },
  { id: 'light', name: 'Clean Minimal', desc: 'Flat light professional', colors: ['#f1f5f9', '#059669', '#ffffff'] },
  { id: 'cyberpunk', name: 'Cyber Neon', desc: 'Neon grid futuristic', colors: ['#0a0014', '#ff0080', '#00ffff'] },
  { id: 'emerald', name: 'Finance Classic', desc: 'Emerald banking style', colors: ['#022c22', '#34d399', '#064e3b'] },
  { id: 'midnight-pro', name: 'Midnight Pro', desc: 'Dense corporate dashboard', colors: ['#0c1222', '#3b82f6', '#1e293b'] },
  { id: 'sunset-warm', name: 'Sunset Warm', desc: 'Cozy gradient cards', colors: ['#1a0a0a', '#f97316', '#7c2d12'] },
  { id: 'terminal', name: 'Terminal Hacker', desc: 'Monospace command line', colors: ['#0a0f0a', '#22c55e', '#14532d'] },
  { id: 'luxury', name: 'Luxury Gold', desc: 'Dark elegant gold accents', colors: ['#0d0d0d', '#d4af37', '#1a1a1a'] },
  { id: 'neumorph', name: 'Soft Neumorph', desc: 'Soft shadows & pills', colors: ['#e0e5ec', '#6366f1', '#f0f3f8'] },
  { id: 'brutalist', name: 'Brutalist Bold', desc: 'Hard edges bold type', colors: ['#fafafa', '#000000', '#ffff00'] },
  { id: 'academy-light', name: 'Academy Light', desc: 'Sidebar + pastel KPI cards', colors: ['#f8fafc', '#059669', '#ecfdf5'], layout: 'sidebar' },
  { id: 'saas-dark-pro', name: 'SaaS Dark Pro', desc: 'Sidebar + dense stats, neon accents', colors: ['#080b14', '#22d3ee', '#0ea5e9'], layout: 'sidebar' },
  { id: 'minimal-admin', name: 'Minimal Admin', desc: 'Sidebar + icon-circle cards, light/dark toggle', colors: ['#fafafa', '#18181b', '#ffffff'], layout: 'sidebar', hasModeToggle: true },
];

/** All modals: [overlayId, wrapId] — used for Escape-to-close. */
const MODAL_REGISTRY = [
  ['modal-overlay', 'phone-modal'],
  ['detail-overlay', 'detail-modal'],
  ['expense-overlay', 'expense-modal'],
  ['acct-overlay', 'acct-modal'],
  ['bank-overlay', 'bank-modal'],
  ['entry-edit-overlay', 'entry-edit-modal'],
  ['partner-overlay', 'partner-modal'],
  ['ps-overlay', 'ps-modal'],
  ['stock-overlay', 'stock-modal'],
  ['welcome-overlay', 'welcome-modal'],
];

function toast(message, type = 'success', duration = 2800) {
  let root = document.getElementById('toast-root');
  if (!root) {
    root = document.createElement('div');
    root.id = 'toast-root';
    document.body.appendChild(root);
  }
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const icon = type === 'success'
    ? '<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>'
    : '<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>';
  el.innerHTML = icon + `<span>${message}</span>`;
  root.appendChild(el);
  setTimeout(() => {
    el.classList.add('out');
    setTimeout(() => el.remove(), 300);
  }, duration);
}

function openModal(overlayId, wrapId) {
  const overlay = document.getElementById(overlayId);
  const wrap = document.getElementById(wrapId);
  if (!overlay || !wrap) return;
  overlay.classList.add('open');
  wrap.classList.add('open');
  document.body.classList.add('modal-open');
}

function closeModal(overlayId, wrapId, onClose) {
  const overlay = document.getElementById(overlayId);
  const wrap = document.getElementById(wrapId);
  if (!overlay || !wrap) return;
  overlay.classList.remove('open');
  wrap.classList.remove('open');
  if (!document.querySelector('.modal-wrap.open')) {
    document.body.classList.remove('modal-open');
  }
  if (onClose) setTimeout(onClose, 280);
}

/** Wire overlay click + optional close button IDs for a modal pair. */
function wireModal(overlayId, wrapId, closeBtnIds = []) {
  document.getElementById(overlayId)?.addEventListener('click', () => closeModal(overlayId, wrapId));
  closeBtnIds.forEach(id => {
    document.getElementById(id)?.addEventListener('click', () => closeModal(overlayId, wrapId));
  });
}

function bumpBadge(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('bump');
  void el.offsetWidth;
  el.classList.add('bump');
}

function animateValue(el, end, formatter, duration = 600) {
  if (!el) return;
  const parsed = Number(end);
  end = Number.isFinite(parsed) ? parsed : 0;
  const start = Number(el.dataset.value);
  const from = Number.isFinite(start) ? start : 0;
  if (from === end) { el.textContent = formatter(end); el.dataset.value = end; return; }
  const t0 = performance.now();
  function step(now) {
    const p = Math.min((now - t0) / duration, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    const val = from + (end - from) * eased;
    el.textContent = formatter(Math.round(val));
    if (p < 1) requestAnimationFrame(step);
    else { el.dataset.value = end; el.textContent = formatter(end); }
  }
  requestAnimationFrame(step);
}

const MODE_KEY = 'crm-theme-mode';

function applyTheme(theme, opts) {
  opts = opts || {};
  const design = UI_DESIGNS.find(t => t.id === theme);
  document.documentElement.setAttribute('data-theme', theme);
  document.documentElement.setAttribute('data-layout', design && design.layout ? design.layout : 'original');
  localStorage.setItem(THEME_KEY, theme);

  const modeBtn = document.getElementById('btn-mode-toggle');
  if (design && design.hasModeToggle) {
    const mode = opts.keepMode ? (localStorage.getItem(MODE_KEY) || 'light') : 'light';
    document.documentElement.setAttribute('data-mode', mode);
    localStorage.setItem(MODE_KEY, mode);
    modeBtn?.classList.remove('hidden');
  } else {
    document.documentElement.removeAttribute('data-mode');
    modeBtn?.classList.add('hidden');
  }

  document.querySelectorAll('.theme-option').forEach(el => {
    el.classList.toggle('active', el.dataset.theme === theme);
  });

  // Sidebar layout only makes sense expanded on desktop; always start closed
  // on mobile widths so it doesn't cover the page.
  const sidebar = document.getElementById('app-sidebar');
  if (sidebar && window.innerWidth <= 900) sidebar.classList.remove('open');
}

function toggleThemeMode() {
  const current = document.documentElement.getAttribute('data-mode') || 'light';
  const next = current === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-mode', next);
  localStorage.setItem(MODE_KEY, next);
}

function renderThemeGrid(container, onPicked) {
  if (!container) return;
  const current = localStorage.getItem(THEME_KEY) || 'default-dark';
  container.innerHTML = UI_DESIGNS.map(t => `
    <button type="button" class="theme-option${t.id === current ? ' active' : ''}" data-theme="${t.id}">
      <div class="theme-preview">
        <span style="background:${t.colors[0]}"></span>
        <span style="background:${t.colors[1]}"></span>
        <span style="background:${t.colors[2]}"></span>
      </div>
      <div class="theme-option-text">
        <p class="theme-option-name">${t.name}</p>
        <p class="theme-option-desc">${t.desc}</p>
      </div>
    </button>`).join('');
  container.querySelectorAll('.theme-option').forEach(btn => {
    btn.addEventListener('click', () => {
      applyTheme(btn.dataset.theme);
      apiFetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: btn.dataset.theme }),
      }).catch(() => {});
      toast(`Design: ${UI_DESIGNS.find(x => x.id === btn.dataset.theme)?.name}`);
      if (onPicked) onPicked();
    });
  });
}

function renderThemeDropdown() {
  renderThemeGrid(document.getElementById('theme-options'), () => {
    document.getElementById('theme-dropdown')?.classList.add('hidden');
  });
}

function initThemePicker() {
  const btn = document.getElementById('theme-picker-btn');
  const dropdown = document.getElementById('theme-dropdown');
  if (!btn || !dropdown) return;
  renderThemeDropdown();
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdown.classList.toggle('hidden');
  });
  document.addEventListener('click', (e) => {
    if (!document.getElementById('theme-picker-wrap')?.contains(e.target)) {
      dropdown.classList.add('hidden');
    }
  });

  document.getElementById('btn-mode-toggle')?.addEventListener('click', toggleThemeMode);
  document.getElementById('btn-sidebar-toggle')?.addEventListener('click', () => {
    document.getElementById('app-sidebar')?.classList.toggle('open');
  });
}

function initSettingsNav() {
  const btn = document.getElementById('btn-settings');
  if (btn) {
    btn.addEventListener('click', () => {
      window.location.href = '/settings';
    });
  }
}

function addShopPhoneRow(value = '') {
  const list = document.getElementById('shop-phones-list');
  if (!list) return;
  const row = document.createElement('div');
  row.className = 'phone-row';
  const input = document.createElement('input');
  input.type = 'tel';
  input.className = 'input-field shop-phone-input';
  input.placeholder = 'e.g. 0300-1234567';
  input.value = value;
  const removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.className = 'btn btn-ghost btn-sm btn-remove-phone';
  removeBtn.setAttribute('aria-label', 'Remove');
  removeBtn.textContent = '✕';
  removeBtn.addEventListener('click', () => {
    const rows = list.querySelectorAll('.phone-row');
    if (rows.length > 1) row.remove();
    else input.value = '';
  });
  row.append(input, removeBtn);
  list.appendChild(row);
  input.focus();
}

function updateBackupStatusLabel(storage) {
  const el = document.getElementById('settings-last-backup');
  if (!el) return;
  el.textContent = storage?.last_backup_at
    ? `Last backup: ${storage.last_backup_at}`
    : 'Last backup: never';
}

async function initSettingsPage() {
  const authForm = document.getElementById('auth-settings-form');
  const storageForm = document.getElementById('storage-settings-form');
  const shopForm = document.getElementById('shop-info-form');
  const emailForm = document.getElementById('email-settings-form');
  if (!authForm) return;

  renderThemeGrid(document.getElementById('settings-theme-options'));
  loadAppVersion();
  initUpdateUi();
  checkForUpdates({ banner: Boolean(document.getElementById('update-banner')) });

  try {
    const shop = await apiFetch('/api/settings/shop');
    document.getElementById('shop-info-name').value = shop.shop_name || '';
    document.getElementById('shop-info-address').value = shop.shop_address || '';
    const waEl = document.getElementById('shop-info-whatsapp');
    if (waEl) waEl.value = shop.shop_whatsapp || '';
    renderShopPhoneRows(shop.shop_phones || []);
  } catch (_) {
    renderShopPhoneRows([]);
  }

  try {
    const auth = await apiFetch('/api/auth/status');
    document.getElementById('settings-username').value = auth.username || auth.session_username || '';
    if (auth.shop_name && !document.getElementById('shop-info-name').value) {
      document.getElementById('shop-info-name').value = auth.shop_name;
    }
  } catch (_) {}

  try {
    const email = await apiFetch('/api/settings/email');
    const gu = document.getElementById('settings-gmail-user');
    const gw = document.getElementById('settings-vendor-wa');
    const gn = document.getElementById('settings-vendor-note');
    if (gu) gu.value = email.gmail_smtp_user || '';
    if (gw) gw.value = email.vendor_whatsapp || '';
    if (gn) gn.value = email.vendor_support_note || '';
  } catch (_) {}

  try {
    const storage = await apiFetch('/api/storage/settings');
    document.getElementById('settings-db-path').textContent = storage.database_path || '—';
    document.getElementById('settings-backup-path').value = storage.local_backup_path || '';
    document.getElementById('settings-auto-backup').checked = storage.auto_backup_enabled !== false;
    updateBackupStatusLabel(storage);
  } catch (err) {
    document.getElementById('settings-db-path').textContent = 'Unable to load path';
  }

  authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await apiFetch('/api/auth/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: document.getElementById('settings-username').value.trim(),
          current_password: document.getElementById('settings-current-pw').value,
          new_password: document.getElementById('settings-new-pw').value || undefined,
        }),
      });
      document.getElementById('settings-current-pw').value = '';
      document.getElementById('settings-new-pw').value = '';
      toast('Login settings saved');
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  emailForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const payload = {
        gmail_smtp_user: document.getElementById('settings-gmail-user').value.trim(),
        vendor_whatsapp: document.getElementById('settings-vendor-wa').value.trim(),
        vendor_support_note: document.getElementById('settings-vendor-note').value.trim(),
      };
      const pass = document.getElementById('settings-gmail-pass').value;
      if (pass) payload.gmail_smtp_app_password = pass;
      await apiFetch('/api/settings/email', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      document.getElementById('settings-gmail-pass').value = '';
      toast('Email settings saved');
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  document.getElementById('btn-test-email')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-test-email');
    btn.disabled = true;
    btn.textContent = 'Sending…';
    try {
      const res = await apiFetch('/api/settings/email/test', { method: 'POST' });
      toast(res.message || 'Test email sent');
    } catch (err) {
      toast(err.message, 'error');
    }
    btn.disabled = false;
    btn.textContent = 'Send Test Email';
  });

  storageForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      await apiFetch('/api/storage/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          local_backup_path: document.getElementById('settings-backup-path').value.trim(),
          auto_backup_enabled: document.getElementById('settings-auto-backup').checked,
        }),
      });
      toast('Backup settings saved');
      refreshBackupList();
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  document.getElementById('btn-export-backup')?.addEventListener('click', () => {
    exportBackup().catch(err => toast(err.message, 'error'));
  });

  document.getElementById('btn-backup-now')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-backup-now');
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = 'Saving…';
    try {
      const backupPath = document.getElementById('settings-backup-path').value.trim();
      if (backupPath) {
        await apiFetch('/api/storage/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ local_backup_path: backupPath }),
        });
      }
      const data = await apiFetch('/api/storage/backup-now', { method: 'POST' });
      updateBackupStatusLabel(data);
      toast('Data saved to backup folder');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Save Data Now';
    }
  });

  document.getElementById('btn-browse-backup')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-browse-backup');
    const input = document.getElementById('settings-backup-path');
    if (!btn || !input) return;
    btn.disabled = true;
    btn.textContent = 'Opening…';
    try {
      const data = await apiFetch('/api/storage/browse-folder', { method: 'POST' });
      if (data.path) {
        input.value = data.path;
        toast('Backup folder selected');
      }
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Browse';
    }
  });

  shopForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const phones = collectShopPhones();
      const payload = {
        shop_name: document.getElementById('shop-info-name').value.trim(),
        shop_address: document.getElementById('shop-info-address').value.trim(),
        shop_phones: phones,
        shop_whatsapp: document.getElementById('shop-info-whatsapp')?.value.trim() || '',
      };
      await apiFetch('/api/settings/shop', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      toast('Shop details saved');
      loadAppBranding();
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  document.getElementById('btn-add-phone')?.addEventListener('click', () => {
    addShopPhoneRow();
  });

  document.getElementById('btn-browse-restore')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-browse-restore');
    const input = document.getElementById('restore-backup-path');
    if (!btn || !input) return;
    btn.disabled = true;
    btn.textContent = 'Opening…';
    try {
      const data = await apiFetch('/api/storage/browse-backup-file', { method: 'POST' });
      if (data.path) {
        input.value = data.path;
        toast('Backup file selected');
      }
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Browse File';
    }
  });

  document.getElementById('btn-restore-backup')?.addEventListener('click', async () => {
    const path = document.getElementById('restore-backup-path')?.value?.trim();
    if (!path) {
      toast('Browse and select a backup file first', 'error');
      return;
    }
    if (!confirm('Restore this backup? Current data will be replaced. You will need to sign in again.')) return;
    try {
      const res = await apiFetch('/api/storage/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ backup_path: path }),
      });
      const safetyNote = res.safety_copy
        ? `\n\nYour previous database was saved here before restoring, just in case:\n${res.safety_copy}`
        : '';
      alert((res.message || 'Restored. Please sign in again.') + safetyNote);
      window.location.href = '/login';
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  document.getElementById('btn-close-crm')?.addEventListener('click', async () => {
    if (!confirm('Close CRM now? The local server will stop and this window will no longer work until you reopen the app.')) return;
    try {
      await apiFetch('/api/system/shutdown', { method: 'POST' });
      document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:system-ui;color:#94a3b8;background:#0f172a"><p>CRM closed. You can close this tab and reopen the app from the desktop.</p></div>';
    } catch (err) {
      toast(err.message, 'error');
    }
  });
}

function renderShopPhoneRows(phones) {
  const list = document.getElementById('shop-phones-list');
  if (!list) return;
  list.innerHTML = '';
  const items = phones.length ? phones : [''];
  items.forEach((phone) => addShopPhoneRow(phone));
}

function collectShopPhones() {
  return [...document.querySelectorAll('.shop-phone-input')]
    .map(el => el.value.trim())
    .filter(Boolean);
}

let _updatePollTimer = null;

function renderUpdatePanel(data, { banner = false } = {}) {
  const statusEl = document.getElementById('update-status-text');
  const notesEl = document.getElementById('update-notes');
  const installBtn = document.getElementById('btn-install-update');
  const manualBtn = document.getElementById('btn-update-manual');
  const bannerEl = document.getElementById('update-banner');
  const bannerText = document.getElementById('update-banner-text');
  const bannerInstall = document.getElementById('update-banner-install');
  const settingsVer = document.getElementById('settings-app-version');

  if (settingsVer && data.current_version) settingsVer.textContent = data.current_version;

  const upToDate = !data.update_available;
  let statusText = upToDate
    ? `You're up to date (version ${data.current_version}).`
    : `New version ${data.remote_version} is ready! You have ${data.current_version}.`;

  if (!data.frozen && data.update_available) {
    statusText += ' Use the compiled desktop app to install in one click.';
  } else if (data.update_available && data.can_auto_install) {
    statusText += ' Click Install update now — takes about a minute.';
  }

  if (statusEl) statusEl.textContent = statusText;

  if (notesEl) {
    if (data.release_notes && data.update_available) {
      notesEl.textContent = data.release_notes;
      notesEl.classList.remove('hidden');
    } else {
      notesEl.classList.add('hidden');
    }
  }

  const showInstall = Boolean(data.update_available && data.can_auto_install);
  if (installBtn) installBtn.classList.toggle('hidden', !showInstall);
  if (bannerInstall) bannerInstall.classList.toggle('hidden', !showInstall);

  const manualUrl = data.download_hint || data.download_url;
  if (manualBtn) {
    manualBtn.classList.toggle('hidden', !(data.update_available && manualUrl));
    if (manualUrl) manualBtn.href = manualUrl;
  }

  if (banner && bannerEl && bannerText) {
    if (data.update_available) {
      bannerEl.classList.remove('hidden');
      if (data.can_auto_install) {
        bannerText.innerHTML = `Update ready: version <strong>${data.remote_version}</strong> (you have ${data.current_version}). Click <strong>Install update</strong> — your Data folder stays safe.`;
      } else {
        bannerText.innerHTML = `Version <strong>${data.remote_version}</strong> is available (you have ${data.current_version}).`;
      }
    } else {
      bannerEl.classList.add('hidden');
    }
  }
}

async function pollUpdateProgress() {
  try {
    const state = await apiFetch('/api/update/status');
    const wrap = document.getElementById('update-progress-wrap');
    const bar = document.getElementById('update-progress-bar');
    const text = document.getElementById('update-progress-text');
    const installBtn = document.getElementById('btn-install-update');
    const checkBtn = document.getElementById('btn-check-updates');

    if (wrap && ['downloading', 'extracting', 'applying', 'restarting', 'checking'].includes(state.status)) {
      wrap.classList.remove('hidden');
      if (bar) bar.style.width = `${state.progress || 0}%`;
      if (text) text.textContent = state.message || 'Working…';
      if (installBtn) installBtn.disabled = true;
      if (checkBtn) checkBtn.disabled = true;
    }

    if (state.status === 'error') {
      if (wrap) wrap.classList.add('hidden');
      if (installBtn) installBtn.disabled = false;
      if (checkBtn) checkBtn.disabled = false;
      toast(state.error || 'Update failed', 'error');
      clearInterval(_updatePollTimer);
      _updatePollTimer = null;
      return;
    }

    if (state.status === 'restarting') {
      if (text) text.textContent = 'Restarting… the app will reopen in a few seconds.';
      clearInterval(_updatePollTimer);
      _updatePollTimer = null;
    }
  } catch (_) {}
}

async function startUpdateInstall() {
  if (!confirm('Install the new version now?\n\n• The app will close for about a minute\n• It will reopen automatically\n• Your shop data (Data folder) is kept safe')) {
    return;
  }
  try {
    await apiFetch('/api/update/install', { method: 'POST' });
    const wrap = document.getElementById('update-progress-wrap');
    if (wrap) wrap.classList.remove('hidden');
    if (!_updatePollTimer) {
      _updatePollTimer = setInterval(pollUpdateProgress, 600);
    }
    pollUpdateProgress();
    toast('Downloading update…', 'success');
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function checkForUpdates(options = {}) {
  const { banner = false } = options;
  try {
    const data = await apiFetch('/api/update/check');
    renderUpdatePanel(data, { banner });
    return data;
  } catch (_) {
    const statusEl = document.getElementById('update-status-text');
    if (statusEl) statusEl.textContent = 'Could not check for updates. Try again later.';
    return null;
  }
}

function initUpdateUi() {
  document.getElementById('btn-check-updates')?.addEventListener('click', () => checkForUpdates());
  document.getElementById('btn-install-update')?.addEventListener('click', startUpdateInstall);
  document.getElementById('update-banner-install')?.addEventListener('click', startUpdateInstall);
}

async function loadAppVersion() {
  try {
    const data = await apiFetch('/api/app/version');
    const el = document.getElementById('app-version');
    if (el && data.version) el.textContent = data.version;
  } catch (_) {}
}

async function loadAppBranding() {
  try {
    const auth = await apiFetch('/api/auth/status');
    const shopEl = document.getElementById('shop-name-display');
    if (shopEl && auth.shop_name) {
      shopEl.textContent = auth.shop_name;
      try { localStorage.setItem('crm-shop-name', auth.shop_name); } catch (_) {}
    }
    const saved = localStorage.getItem(THEME_KEY);
    // Always apply (not just on mismatch) so data-layout/data-mode get
    // computed by the real applyTheme() logic on every load — the inline
    // pre-paint script in base.html only sets data-theme, not layout/mode.
    applyTheme(auth.theme || saved || 'default-dark', { keepMode: true });
    return auth;
  } catch (_) {
    return null;
  }
}

function showWelcomeModal(username, shopName) {
  const title = document.getElementById('welcome-title');
  const subtitle = document.getElementById('welcome-subtitle');
  if (title) title.textContent = `Welcome, ${username || 'User'}`;
  if (subtitle) subtitle.textContent = shopName ? `${shopName} is ready.` : 'Your CRM is ready.';
  setTimeout(() => {
    openModal('welcome-overlay', 'welcome-modal');
    toast(`Welcome, ${username || 'User'}`, 'success', 4000);
  }, 350);
}

function initWelcome() {
  wireModal('welcome-overlay', 'welcome-modal', ['welcome-dismiss', 'welcome-close-x']);
}

function initModalEscapeHandler() {
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    MODAL_REGISTRY.forEach(([overlayId, wrapId]) => {
      const wrap = document.getElementById(wrapId);
      if (wrap && wrap.classList.contains('open')) {
        closeModal(overlayId, wrapId);
      }
    });
    document.getElementById('theme-dropdown')?.classList.add('hidden');
  });
}

function initPageTransitions() {
  // Subtle fade-out before a same-tab internal navigation, so the page
  // change feels like one continuous transition instead of an abrupt
  // white/dark flash between server-rendered pages. Kept short (120ms) so
  // it never feels like it's slowing navigation down.
  document.addEventListener('click', (e) => {
    const link = e.target.closest('a[href]');
    if (!link) return;
    const url = new URL(link.href, window.location.href);
    const isInternal = url.origin === window.location.origin;
    const opensNewTab = link.target === '_blank' || e.metaKey || e.ctrlKey || e.shiftKey;
    if (!isInternal || opensNewTab || link.hasAttribute('download')) return;
    const main = document.querySelector('.page-enter');
    if (!main) return;
    e.preventDefault();
    main.classList.add('page-leave');
    setTimeout(() => { window.location.href = link.href; }, 120);
  });
}

async function initApp() {
  initModalEscapeHandler();
  initWelcome();
  initThemePicker();
  initSettingsNav();
  initPageTransitions();
  checkForUpdates({ banner: true });
  const auth = await loadAppBranding();
  if (auth?.show_welcome) {
    showWelcomeModal(auth.session_username || auth.username, auth.shop_name);
  }
}

async function exportBackup() {
  const data = await apiFetch('/api/backup/export');
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `crm-backup-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  toast('Backup exported');
}

function _escSelectHtml(text) {
  const el = document.createElement('div');
  el.textContent = text || '';
  return el.innerHTML;
}

/**
 * Searchable account picker — use in Journal, Cash Book, Accounts.
 * Returns { setAccounts, getValue, getLabel, reset, requireSelection }.
 */
function createSearchableAccountSelect(container, options = {}) {
  const {
    placeholder = 'Search account…',
    allowEmpty = false,
    emptyLabel = '— None —',
    onSelect = null,
  } = options;

  if (typeof container === 'string') {
    container = document.getElementById(container);
  }
  if (!container) return null;

  container.classList.add('searchable-select-wrap');
  container.innerHTML = `
    <input type="text" class="input-field searchable-select-input" placeholder="${placeholder}" autocomplete="off">
    <input type="hidden" class="searchable-select-value" value="">
    <div class="searchable-select-dropdown hidden" role="listbox"></div>`;

  const input = container.querySelector('.searchable-select-input');
  const hidden = container.querySelector('.searchable-select-value');
  const dropdown = container.querySelector('.searchable-select-dropdown');
  let accounts = [];

  function renderList(filter = '') {
    const q = filter.trim().toLowerCase();
    const filtered = accounts.filter((a) => {
      const name = (a.name || '').toLowerCase();
      const contact = (a.contact || '').toLowerCase();
      return !q || name.includes(q) || contact.includes(q);
    });

    let html = '';
    if (allowEmpty && (!q || emptyLabel.toLowerCase().includes(q))) {
      html += `<button type="button" class="searchable-select-option" data-id="" data-name="${_escSelectHtml(emptyLabel)}">${_escSelectHtml(emptyLabel)}</button>`;
    }
    html += filtered.map((a) => `
      <button type="button" class="searchable-select-option" data-id="${a.id}" data-name="${_escSelectHtml(a.name)}">
        ${_escSelectHtml(a.name)}${a.contact ? `<span class="text-slate-500 text-xs ml-1">${_escSelectHtml(a.contact)}</span>` : ''}
      </button>`).join('');
    if (!html) {
      html = '<div class="searchable-select-empty">No accounts found</div>';
    }
    dropdown.innerHTML = html;
  }

  function openDropdown() {
    dropdown.classList.remove('hidden');
    renderList(input.value);
  }

  function closeDropdown() {
    dropdown.classList.add('hidden');
  }

  function pick(id, name) {
    hidden.value = id;
    input.value = name || '';
    closeDropdown();
    if (typeof onSelect === 'function') onSelect(id, name);
  }

  input.addEventListener('focus', openDropdown);
  input.addEventListener('click', openDropdown);
  input.addEventListener('input', () => {
    hidden.value = '';
    openDropdown();
  });

  dropdown.addEventListener('mousedown', (e) => {
    const btn = e.target.closest('.searchable-select-option');
    if (!btn) return;
    e.preventDefault();
    pick(btn.dataset.id || '', btn.dataset.name || btn.textContent.trim());
  });

  document.addEventListener('click', (e) => {
    if (!container.contains(e.target)) closeDropdown();
  });

  return {
    setAccounts(list) {
      accounts = list || [];
    },
    getValue() {
      return hidden.value;
    },
    getLabel() {
      return input.value.trim();
    },
    reset() {
      hidden.value = '';
      input.value = '';
      closeDropdown();
    },
    setValue(id) {
      if (!id) {
        hidden.value = '';
        input.value = allowEmpty ? emptyLabel : '';
        closeDropdown();
        return;
      }
      const acct = accounts.find((a) => String(a.id) === String(id));
      if (acct) {
        pick(String(acct.id), acct.name);
      }
    },
    requireSelection(message = 'Please select an account from the list') {
      if (hidden.value || allowEmpty) return true;
      toast(message, 'error');
      input.focus();
      return false;
    },
  };
}

window.createSearchableAccountSelect = createSearchableAccountSelect;

const CONDITION_OPTIONS = [
  '10/10', '10/9.5', '10/9', '10/8.5', '10/8', '10/7.5',
  '10/7', '10/6.5', '10/6', '10/5.5', '10/5',
];

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('shop-name-display')) {
    initApp();
  } else {
    const saved = localStorage.getItem(THEME_KEY) || 'default-dark';
    applyTheme(saved);
  }
});
