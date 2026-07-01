/** Global JSON API helper — loaded before page scripts that call apiFetch. */
async function apiFetch(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && data.needs_setup) {
    window.location.href = '/login';
    throw new Error('Setup required');
  }
  if (res.status === 401 && !url.includes('/auth/')) {
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }
  if (!res.ok) throw new Error(data.error || 'Something went wrong');
  return data;
}

window.apiFetch = apiFetch;
