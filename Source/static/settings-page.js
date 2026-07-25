/* Settings page UI — loaded from templates/settings.html (and base if needed).

Wires shop details, backup folder picker, email/SMTP, logo upload, and
related Settings-only controls. Shared helpers (toast, apiFetch, theme,
updates) stay in ui.js.
*/

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
  checkForUpdatesAuto({ banner: Boolean(document.getElementById('update-banner')) });

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
      // Backup folder list UI removed; status label refreshes on Save Data Now.
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

