/* Shared UI utilities */

const THEME_KEY = 'crm-theme';

const UI_DESIGNS = [
  { id: 'default-dark', name: 'Glass Dark', desc: 'Frosted glass morphism', colors: ['#030712', '#10b981', '#0f172a'] },
  { id: 'light', name: 'Clean Minimal', desc: 'Flat light professional', colors: ['#f1f5f9', '#059669', '#ffffff'] },
  { id: 'cyberpunk', name: 'Cyber Neon', desc: 'Neon grid futuristic', colors: ['#0a0014', '#ff0080', '#00ffff'] },
  { id: 'emerald', name: 'Finance Classic', desc: 'Emerald banking style', colors: ['#022c22', '#34d399', '#064e3b'] },
  { id: 'midnight-pro', name: 'Midnight Pro', desc: 'Dense corporate dashboard', colors: ['#0c1222', '#3b82f6', '#1e293b'] },
  { id: 'sunset-warm', name: 'Sunset Warm', desc: 'Cozy gradient cards', colors: ['#1a0a0a', '#f97316', '#7c2d12'] },
  { id: 'terminal', name: 'Terminal Hacker', desc: 'Monospace command line', colors: ['#0a0f0a', '#22c55e', '#14532d'] },
  { id: 'luxury', name: 'Luxury Gold', desc: 'Dark elegant gold accents', colors: ['#0d0d0d', '#d4af37', '#1a1a1a'] },
  { id: 'neumorph', name: 'Soft Neumorph', desc: 'Soft shadows & pills', colors: ['#e0e5ec', '#6366f1', '#f0f3f8'] },
  { id: 'brutalist', name: 'Brutalist Bold', desc: 'Hard edges bold type', colors: ['#fafafa', '#000000', '#ffff00'] },
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
  const start = parseFloat(el.dataset.value) || 0;
  if (start === end) { el.textContent = formatter(end); return; }
  const t0 = performance.now();
  function step(now) {
    const p = Math.min((now - t0) / duration, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    const val = start + (end - start) * eased;
    el.textContent = formatter(Math.round(val));
    if (p < 1) requestAnimationFrame(step);
    else { el.dataset.value = end; el.textContent = formatter(end); }
  }
  requestAnimationFrame(step);
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem(THEME_KEY, theme);
  document.querySelectorAll('.theme-option').forEach(el => {
    el.classList.toggle('active', el.dataset.theme === theme);
  });
}

function renderThemeDropdown() {
  const grid = document.getElementById('theme-options');
  if (!grid) return;
  const current = localStorage.getItem(THEME_KEY) || 'default-dark';
  grid.innerHTML = UI_DESIGNS.map(t => `
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
  grid.querySelectorAll('.theme-option').forEach(btn => {
    btn.addEventListener('click', () => {
      applyTheme(btn.dataset.theme);
      apiFetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: btn.dataset.theme }),
      }).catch(() => {});
      document.getElementById('theme-dropdown')?.classList.add('hidden');
      toast(`Design: ${UI_DESIGNS.find(x => x.id === btn.dataset.theme)?.name}`);
    });
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
      alert(res.message || 'Restored. Please sign in again.');
      window.location.href = '/login';
    } catch (err) {
      toast(err.message, 'error');
    }
  });

  document.getElementById('btn-close-crm')?.addEventListener('click', async () => {
    if (!confirm('Close CRM now? The local server will stop and this window will no longer work until you reopen the app.')) return;
    try {
      const res = await apiFetch('/api/system/shutdown', { method: 'POST' });
      alert(res.message || 'CRM is closing...');
      setTimeout(() => {
        window.close();
      }, 600);
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

async function checkForUpdates() {
  const banner = document.getElementById('update-banner');
  const text = document.getElementById('update-banner-text');
  if (!banner) return;
  try {
    const data = await apiFetch('/api/update/check');
    if (data.update_available) {
      banner.classList.remove('hidden');
      text.textContent = `Version ${data.remote_version} is available (you have ${data.current_version}). Download the latest build from GitHub.`;
    }
  } catch (_) {}
}

async function loadAppBranding() {
  try {
    const auth = await apiFetch('/api/auth/status');
    const shopEl = document.getElementById('shop-name-display');
    if (shopEl && auth.shop_name) shopEl.textContent = auth.shop_name;
    const saved = localStorage.getItem(THEME_KEY);
    if (auth.theme && auth.theme !== saved) {
      applyTheme(auth.theme);
    }
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

async function initApp() {
  initModalEscapeHandler();
  initWelcome();
  initThemePicker();
  initSettingsNav();
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
