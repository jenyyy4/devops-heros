// The browser always calls the API same-origin (/api). nginx (Docker Compose) or the
// Kubernetes Ingress routes it to the FastAPI service, so no backend hostname lives here.
const BASE = '/api';

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail) ? detail.map((d) => `${d.loc?.at(-1)}: ${d.msg}`).join('; ') : detail;
    throw new Error(message || `Request failed (${response.status})`);
  }
  return data;
}

export const api = {
  stats: (date) => request(`/appointments/stats?date=${date}`),
  appointments: (date) => request(`/appointments?date=${date}`),
  book: (payload) => request('/appointments', { method: 'POST', body: payload }),
  updateAppointment: (id, payload) => request(`/appointments/${id}`, { method: 'PUT', body: payload }),
  patients: (search = '') => request(`/patients${search ? `?search=${encodeURIComponent(search)}` : ''}`),
  registerPatient: (payload) => request('/patients', { method: 'POST', body: payload }),
  deletePatient: (id) => request(`/patients/${id}`, { method: 'DELETE' }),
  doctors: () => request('/doctors'),
  updateDoctor: (id, payload) => request(`/doctors/${id}`, { method: 'PUT', body: payload }),
};
