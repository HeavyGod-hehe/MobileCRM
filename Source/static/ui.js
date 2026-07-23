/* Shared UI utilities — loaded on every page (see templates/base.html).

BEGINNER'S MAP OF THIS FILE
----------------------------
Plain JavaScript (no framework/build step) that every CRM page shares:

  - toast / openModal / closeModal / wireModal / bumpBadge — small generic
    helpers used all over the app (notifications, popup forms).
  - applyTheme / toggleTheme — the light/dark switcher (top bar + Settings
    -> Appearance). "Theme" is just the data-theme attribute on <html>
    (see static/app.css) plus a value saved to localStorage (THEME_KEY) so
    it persists across page loads.
  - initSettingsPage (the biggest function here) — wires up every control
    on the Settings page: shop details, backup folder picker, email/SMTP
    config, license info, and the update-checker UI below.
  - checkForUpdates / startUpdateInstall / pollUpdateProgress /
    renderUpdatePanel — talk to the /api/app/... routes backed by
    update_service.py on the server; this is the polling loop that shows a
    live progress bar while an update downloads and installs.
  - createSearchableAccountSelect — a reusable "type to filter" dropdown
    used anywhere the user needs to pick a customer/supplier account.
  - initApp — called at the bottom of every page; wires up the bits every
    page needs (theme, modals, page-transition animation, welcome popup).
*/

const THEME_KEY = 'crm-theme';

// The app now ships a single design (Retailer-POS-inspired light look) with
// an optional dark mode — the old 14-skin picker is gone. Existing accounts
// may still have an old theme id (e.g. "default-dark", "cyberpunk") saved
// server-side; normalizeTheme maps anything that isn't literally "dark" to
// the new default "light" look.
function normalizeTheme(theme) {
  return theme === 'dark' ? 'dark' : 'light';
}

/** All modals: [overlayId, wrapId] — used for Escape-to-close.
 * Bug #25: 6 modals opened via openModal() were missing here, so Escape
 * silently did nothing on them (backdrop click / X / Cancel still worked).
 * Any new openModal(overlayId, wrapId) call must add its pair here too. */
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
  ['payment-pick-overlay', 'payment-pick-modal'],
  ['inv-acct-overlay', 'inv-acct-modal'],
  ['bulk-sold-overlay', 'bulk-sold-modal'],
  ['jv-acct-overlay', 'jv-acct-modal'],
  ['reinvest-overlay', 'reinvest-modal'],
  ['side-inv-overlay', 'side-inv-modal'],
  ['imei-scanner-overlay', 'imei-scanner-modal'],
  ['pi-scanner-overlay', 'pi-scanner-modal'],
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

// Small dependency-free canvas bar chart — no charting library, no build
// step, matches the rest of this file's plain-JS approach. `items` is
// [{label, value}]; only ever fed real numbers already fetched from an
// API, never invented data.
function renderBarChart(canvas, items, opts = {}) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = canvas.clientWidth || canvas.parentElement?.clientWidth || 300;
  const cssHeight = opts.height || 180;
  canvas.width = cssWidth * dpr;
  canvas.height = cssHeight * dpr;
  canvas.style.height = cssHeight + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);
  if (!items.length) return;

  const color = opts.color || '#2563eb';
  const max = Math.max(...items.map(i => i.value), 1);
  const padTop = 26, padBottom = 28, padX = 8;
  const chartH = cssHeight - padTop - padBottom;
  const gap = 12;
  const n = items.length;
  const barW = Math.max(10, Math.min(52, (cssWidth - padX * 2 - gap * (n + 1)) / n));
  const totalW = barW * n + gap * (n - 1);
  let x = (cssWidth - totalW) / 2;

  // Soft baseline
  ctx.strokeStyle = 'rgba(148, 163, 184, 0.25)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padX, padTop + chartH);
  ctx.lineTo(cssWidth - padX, padTop + chartH);
  ctx.stroke();

  items.forEach(item => {
    const h = Math.max(4, (item.value / max) * chartH);
    const y = padTop + (chartH - h);
    const r = Math.min(8, barW / 2);

    const grad = ctx.createLinearGradient(x, y, x, y + h);
    grad.addColorStop(0, color);
    grad.addColorStop(1, opts.colorEnd || '#60a5fa');
    ctx.fillStyle = grad;

    ctx.beginPath();
    ctx.moveTo(x, y + h);
    ctx.lineTo(x, y + r);
    ctx.arcTo(x, y, x + r, y, r);
    ctx.lineTo(x + barW - r, y);
    ctx.arcTo(x + barW, y, x + barW, y + r, r);
    ctx.lineTo(x + barW, y + h);
    ctx.closePath();
    ctx.fill();

    ctx.textAlign = 'center';
    ctx.fillStyle = opts.labelColor || '#475569';
    ctx.font = '600 10px -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif';
    const valueText = opts.formatValue ? opts.formatValue(item.value) : String(item.value);
    ctx.fillText(valueText, x + barW / 2, Math.max(12, y - 8));

    ctx.fillStyle = opts.axisColor || '#94a3b8';
    ctx.font = '500 9px -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif';
    const label = (item.label || '').length > 9 ? item.label.slice(0, 8) + '…' : (item.label || '');
    ctx.fillText(label, x + barW / 2, cssHeight - 10);

    x += barW + gap;
  });
}
window.renderBarChart = renderBarChart;

// Switch to `theme` ('light' or 'dark'): sets data-theme on <html> (app.css
// keys off it) and remembers the choice in localStorage so it survives a
// page reload.
function applyTheme(theme) {
  const mode = normalizeTheme(theme);
  document.documentElement.setAttribute('data-theme', mode);
  document.documentElement.setAttribute('data-layout', 'sidebar');
  localStorage.setItem(THEME_KEY, mode);

  document.querySelectorAll('.theme-mode-option').forEach(el => {
    el.classList.toggle('active', el.dataset.theme === mode);
  });

  // Sidebar only makes sense expanded on desktop; always start closed on
  // mobile widths so it doesn't cover the page.
  if (window.innerWidth < 1024) setSidebarOpen(false);
}

/** Bug #26: the mobile sidebar drawer had no backdrop and no outside-tap/
 * Escape dismiss — the hamburger button was the only way to close it.
 * This keeps the backdrop's open state in sync with the sidebar's. */
function setSidebarOpen(open) {
  document.getElementById('app-sidebar')?.classList.toggle('open', open);
  document.getElementById('sidebar-backdrop')?.classList.toggle('open', open);
}

function toggleTheme() {
  const current = normalizeTheme(document.documentElement.getAttribute('data-theme'));
  const next = current === 'light' ? 'dark' : 'light';
  applyTheme(next);
  apiFetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ theme: next }),
  }).catch(() => {});
}

// Renders the light/dark toggle used on the Settings page's Appearance
// section (the top-bar sun/moon icon is the same toggle, just icon-only).
function renderThemeGrid(container) {
  if (!container) return;
  const current = normalizeTheme(localStorage.getItem(THEME_KEY));
  container.innerHTML = ['light', 'dark'].map(id => `
    <button type="button" class="filter-tab theme-mode-option${id === current ? ' active' : ''}" data-theme="${id}">
      ${id === 'light' ? 'Light' : 'Dark'}
    </button>`).join('');
  container.querySelectorAll('.theme-mode-option').forEach(btn => {
    btn.addEventListener('click', () => {
      applyTheme(btn.dataset.theme);
      toast(`Appearance: ${btn.dataset.theme === 'dark' ? 'Dark' : 'Light'}`);
    });
  });
}

function initTopBarControls() {
  document.getElementById('btn-mode-toggle')?.addEventListener('click', toggleTheme);
  document.getElementById('btn-sidebar-toggle')?.addEventListener('click', () => {
    const isOpen = document.getElementById('app-sidebar')?.classList.contains('open');
    setSidebarOpen(!isOpen);
  });
  document.getElementById('sidebar-backdrop')?.addEventListener('click', () => setSidebarOpen(false));

  // Global search: jumps to Inventory with the query pre-filled — it reuses
  // Inventory's own existing client-side search rather than pretending to
  // search everything (no cross-page search API exists).
  document.getElementById('nav-search-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const q = document.getElementById('nav-search-input')?.value.trim();
    window.location.href = q ? `/inventory?q=${encodeURIComponent(q)}` : '/inventory';
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

// Read an uploaded logo image, crop it to a centered square, downscale it
// to `size`x`size` (via an off-screen <canvas>), and return it as a data:
// URL — this keeps uploaded shop logos small and consistently sized without
// needing a server-side image library.
function resizeImageFileToSquareDataUrl(file, size = 200) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Could not read that file.'));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error('That file is not a valid image.'));
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        const scale = Math.max(size / img.width, size / img.height);
        const drawW = img.width * scale;
        const drawH = img.height * scale;
        ctx.drawImage(img, (size - drawW) / 2, (size - drawH) / 2, drawW, drawH);
        resolve(canvas.toDataURL('image/png'));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

function setShopLogoPreview(dataUrl) {
  const img = document.getElementById('shop-logo-preview');
  const fallback = document.getElementById('shop-logo-preview-default');
  const removeBtn = document.getElementById('btn-remove-logo');
  if (!img) return;
  if (dataUrl) {
    img.src = dataUrl;
    img.classList.remove('hidden');
    fallback?.classList.add('hidden');
    removeBtn?.classList.remove('hidden');
  } else {
    img.classList.add('hidden');
    img.removeAttribute('src');
    fallback?.classList.remove('hidden');
    removeBtn?.classList.add('hidden');
  }
}

function updateBackupStatusLabel(storage) {
  const el = document.getElementById('settings-last-backup');
  if (!el) return;
  el.textContent = storage?.last_backup_at
    ? `Last backup: ${storage.last_backup_at}`
    : 'Last backup: never';
}

// Wires up every control on the Settings page. Guarded by `if (!authForm)
// return` below so this is a no-op on any other page (this script is
// shared/loaded everywhere, but the Settings-specific elements only exist
// in templates/settings.html).
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
    setShopLogoPreview(shop.shop_logo || '');
    const cashEl = document.getElementById('shop-info-cash-opening');
    if (cashEl) cashEl.value = shop.cash_in_hand ?? 0;
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
      const cashEl = document.getElementById('shop-info-cash-opening');
      const payload = {
        shop_name: document.getElementById('shop-info-name').value.trim(),
        shop_address: document.getElementById('shop-info-address').value.trim(),
        shop_phones: phones,
        shop_whatsapp: document.getElementById('shop-info-whatsapp')?.value.trim() || '',
      };
      if (cashEl) payload.cash_in_hand = cashEl.value;
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

  document.getElementById('btn-upload-logo')?.addEventListener('click', () => {
    document.getElementById('shop-logo-file')?.click();
  });

  document.getElementById('shop-logo-file')?.addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    try {
      const dataUrl = await resizeImageFileToSquareDataUrl(file);
      await apiFetch('/api/settings/logo', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shop_logo: dataUrl }),
      });
      setShopLogoPreview(dataUrl);
      toast('Logo updated');
      loadAppBranding();
    } catch (err) {
      toast(err.message || 'Could not upload that logo', 'error');
    }
  });

  document.getElementById('btn-remove-logo')?.addEventListener('click', async () => {
    try {
      await apiFetch('/api/settings/logo', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shop_logo: '' }),
      });
      setShopLogoPreview('');
      toast('Logo removed');
      loadAppBranding();
    } catch (err) {
      toast(err.message || 'Could not remove logo', 'error');
    }
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

// Paint the Settings-page update section AND (if banner=true) the small
// top-of-page banner, from one check-for-updates response (see
// checkForUpdates() below / update_service.check_for_updates() on the
// server). Shared by both because they show the same info in two places.
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

// Called every second (see initUpdateUi below) once an install has
// started, to move the progress bar. Talks to the SAME backend state that
// update_service.py's _install_worker() thread updates as it downloads/
// extracts/applies the update, so this is effectively watching that
// background thread's progress from the browser.
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

// Kicks off the actual download+install (see /api/update/install ->
// update_service.start_install(), which runs it on a background thread
// server-side) and starts polling for progress every 600ms.
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

// Asks the server "is there a newer version?" (see /api/update/check ->
// update_service.check_for_updates()) and repaints the UI with the answer.
// Called on every page load (quiet banner check) and by the explicit
// "Check for updates" button on Settings.
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
    const shopEls = document.querySelectorAll('.shop-name-display');
    if (shopEls.length && auth.shop_name) {
      shopEls.forEach((el) => { el.textContent = auth.shop_name; });
      try { localStorage.setItem('crm-shop-name', auth.shop_name); } catch (_) {}
    }
    const logoImg = document.getElementById('nav-logo-img');
    const logoDefault = document.getElementById('nav-logo-default');
    if (logoImg && logoDefault) {
      if (auth.shop_logo) {
        logoImg.src = auth.shop_logo;
        logoImg.classList.remove('hidden');
        logoDefault.classList.add('hidden');
      } else {
        logoImg.classList.add('hidden');
        logoImg.removeAttribute('src');
        logoDefault.classList.remove('hidden');
      }
    }
    // This browser's own last choice wins over the server-stored value —
    // otherwise a toggle click gets silently reverted on the next page
    // load if the /api/settings PUT hasn't landed yet (or for any other
    // reason lags behind). Server value is only the fallback for a
    // browser that has never set a local preference.
    const saved = localStorage.getItem(THEME_KEY);
    applyTheme(saved || auth.theme || 'light');
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
    if (document.getElementById('app-sidebar')?.classList.contains('open')) {
      setSidebarOpen(false);
    }
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
  initTopBarControls();
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
  if (document.querySelector('.shop-name-display')) {
    initApp();
  } else {
    applyTheme(localStorage.getItem(THEME_KEY));
  }
});
