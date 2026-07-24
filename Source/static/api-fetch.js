/** Global JSON API helper — loaded before page scripts that call apiFetch.
 *
 * Every request gets a client-side timeout: without one, a request that
 * never resolves (server momentarily unresponsive, a dropped local
 * connection) just leaves the caller's spinner running forever with no
 * error and nothing to recover from - reported by real customers as the
 * app "getting stuck on Signup." 20s comfortably covers every real call
 * site (the only two long-running operations - backup restore and the
 * update installer - already return immediately and report progress via
 * separate polling, they don't hold the request open).
 *
 * A raw network failure (fetch() throwing TypeError "Failed to fetch", or
 * our own timeout firing an AbortError) is caught here and turned into one
 * plain-language message instead of leaking the raw browser error text to
 * the user via whatever toast/alert the caller shows it in.
 */
const API_FETCH_TIMEOUT_MS = 20000;

async function apiFetch(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), API_FETCH_TIMEOUT_MS);
  let res;
  try {
    res = await fetch(url, { ...options, signal: controller.signal });
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('The app took too long to respond — please try again.');
    }
    throw new Error('Couldn\'t reach the app — make sure it\'s still running and try again.');
  } finally {
    clearTimeout(timer);
  }
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
