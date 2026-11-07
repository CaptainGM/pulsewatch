const API_BASE = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '');
const TOKEN_KEY = 'pulsewatch.token';
export const AUTH_REQUIRED_EVENT = 'pulsewatch:auth-required';

export function getToken() {
  try {
    return window.localStorage.getItem(TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function setToken(token) {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
  }
}

export function clearToken() {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
  }
}

async function readError(response) {
  let detail = '';
  try {
    const data = await response.json();
    if (typeof data.detail === 'string') {
      detail = data.detail;
    } else if (Array.isArray(data.detail)) {
      detail = data.detail.map((item) => item.msg).join(', ');
    }
  } catch {
  }
  return detail || `İstek başarısız (HTTP ${response.status})`;
}

async function requestOnce(path, { method = 'GET', body, signal } = {}) {
  const token = getToken();
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    const networkError = new Error('Sunucuya ulaşılamadı. Backend çalışıyor mu?');
    networkError.network = true;
    throw networkError;
  }

  if (response.status === 401 && token && !path.startsWith('/auth/login')) {
    clearToken();
    window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
  }

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  if (response.status === 204) return null;
  return response.json();
}

const RETRY_DELAYS = [400, 1200];

async function request(path, options = {}) {
  const retryable = (options.method || 'GET') === 'GET';
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await requestOnce(path, options);
    } catch (error) {
      if (!retryable || !error.network || attempt >= RETRY_DELAYS.length) throw error;
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS[attempt]));
    }
  }
}

export async function downloadFile(path, filename) {
  const token = getToken();
  const response = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) throw new Error(await readError(response));
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function takeOAuthFragment() {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const token = params.get('oauth_token');
  const error = params.get('oauth_error');
  if (!token && !error) return null;
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
  return { token, error };
}

export const api = {
  authConfig: (signal) => request('/auth/config', { signal }),
  login: (email, password) => request('/auth/login', { method: 'POST', body: { email, password } }),
  me: (signal) => request('/auth/me', { signal }),

  dashboard: (signal) => request('/dashboard', { signal }),
  monitors: (signal) => request('/monitors', { signal }),
  monitor: (id, signal) => request(`/monitors/${id}`, { signal }),
  createMonitor: (payload) => request('/monitors', { method: 'POST', body: payload }),
  updateMonitor: (id, payload) => request(`/monitors/${id}`, { method: 'PATCH', body: payload }),
  deleteMonitor: (id) => request(`/monitors/${id}`, { method: 'DELETE' }),
  checkNow: (id) => request(`/monitors/${id}/check`, { method: 'POST' }),
  checks: (id, { limit = 50, offset = 0 } = {}, signal) =>
    request(`/monitors/${id}/checks?limit=${limit}&offset=${offset}`, { signal }),
  stats: (id, { hours = 24, buckets = 48 } = {}, signal) =>
    request(`/monitors/${id}/stats?hours=${hours}&buckets=${buckets}`, { signal }),
  monitorRegions: (id, signal) => request(`/monitors/${id}/regions`, { signal }),
  importMonitors: (monitors) => request('/monitors/import', { method: 'POST', body: { monitors } }),

  incidents: (params = {}, signal) => {
    const query = new URLSearchParams(
      Object.entries(params).filter(
        ([, value]) => value !== undefined && value !== null && value !== '',
      ),
    ).toString();
    return request(`/incidents${query ? `?${query}` : ''}`, { signal });
  },
  acknowledgeIncident: (id) => request(`/incidents/${id}/ack`, { method: 'POST' }),

  notifications: (signal) => request('/notifications?limit=50', { signal }),
  markNotificationRead: (id) => request(`/notifications/${id}/read`, { method: 'PATCH' }),
  markAllNotificationsRead: () => request('/notifications/read-all', { method: 'POST' }),
  testWebhook: (url) => request('/notifications/test-webhook', { method: 'POST', body: { url } }),

  statusPage: (signal) => request('/status-page', { signal }),
  site: (signal) => request('/site', { signal }),
  saveSite: (payload) => request('/site', { method: 'PUT', body: payload }),

  maintenance: (signal) => request('/maintenance', { signal }),
  createMaintenance: (payload) => request('/maintenance', { method: 'POST', body: payload }),
  deleteMaintenance: (id) => request(`/maintenance/${id}`, { method: 'DELETE' }),

  users: (signal) => request('/users', { signal }),
  createUser: (payload) => request('/users', { method: 'POST', body: payload }),
  updateUser: (id, payload) => request(`/users/${id}`, { method: 'PATCH', body: payload }),
  deleteUser: (id) => request(`/users/${id}`, { method: 'DELETE' }),

  sla: (days, signal) => request(`/sla?days=${days}`, { signal }),

  channels: (signal) => request('/channels', { signal }),
  createChannel: (payload) => request('/channels', { method: 'POST', body: payload }),
  updateChannel: (id, payload) => request(`/channels/${id}`, { method: 'PATCH', body: payload }),
  deleteChannel: (id) => request(`/channels/${id}`, { method: 'DELETE' }),
  testChannel: (id) => request(`/channels/${id}/test`, { method: 'POST' }),

  apiKeys: (signal) => request('/api-keys', { signal }),
  createApiKey: (name) => request('/api-keys', { method: 'POST', body: { name } }),
  deleteApiKey: (id) => request(`/api-keys/${id}`, { method: 'DELETE' }),
};

function websocketBase() {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL;
  if (API_BASE.startsWith('http')) {
    const url = new URL(API_BASE);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.pathname = `${url.pathname.replace(/\/$/, '')}/ws`;
    return url.toString();
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}${API_BASE}/ws`;
}

export function getWebSocketUrl() {
  const base = websocketBase();
  const token = getToken();
  if (!token) return base;
  return `${base}${base.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`;
}
