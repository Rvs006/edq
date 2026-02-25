/**
 * API Client — Axios instance with JWT auth interceptors.
 */

import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
})

// Request interceptor — attach JWT token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('edq_access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor — handle 401 and token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      const refreshToken = localStorage.getItem('edq_refresh_token')
      if (refreshToken) {
        try {
          const { data } = await axios.post(`${API_BASE}/auth/refresh`, {
            refresh_token: refreshToken,
          })
          localStorage.setItem('edq_access_token', data.access_token)
          localStorage.setItem('edq_refresh_token', data.refresh_token)
          originalRequest.headers.Authorization = `Bearer ${data.access_token}`
          return api(originalRequest)
        } catch {
          localStorage.removeItem('edq_access_token')
          localStorage.removeItem('edq_refresh_token')
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(error)
  }
)

export default api

// --- Auth ---
export const authApi = {
  login: (data: { username: string; password: string }) => api.post('/auth/login', data),
  register: (data: any) => api.post('/auth/register', data),
  me: () => api.get('/auth/me'),
  changePassword: (data: any) => api.post('/auth/change-password', data),
}

// --- Devices ---
export const devicesApi = {
  list: (params?: any) => api.get('/devices/', { params }),
  get: (id: string) => api.get(`/devices/${id}`),
  create: (data: any) => api.post('/devices/', data),
  update: (id: string, data: any) => api.patch(`/devices/${id}`, data),
  delete: (id: string) => api.delete(`/devices/${id}`),
  stats: () => api.get('/devices/stats'),
}

// --- Device Profiles ---
export const profilesApi = {
  list: (params?: any) => api.get('/device-profiles/', { params }),
  get: (id: string) => api.get(`/device-profiles/${id}`),
  create: (data: any) => api.post('/device-profiles/', data),
  update: (id: string, data: any) => api.patch(`/device-profiles/${id}`, data),
  delete: (id: string) => api.delete(`/device-profiles/${id}`),
}

// --- Test Templates ---
export const templatesApi = {
  list: () => api.get('/test-templates/'),
  get: (id: string) => api.get(`/test-templates/${id}`),
  create: (data: any) => api.post('/test-templates/', data),
  update: (id: string, data: any) => api.patch(`/test-templates/${id}`, data),
  delete: (id: string) => api.delete(`/test-templates/${id}`),
  library: () => api.get('/test-templates/library'),
}

// --- Test Runs ---
export const testRunsApi = {
  list: (params?: any) => api.get('/test-runs/', { params }),
  get: (id: string) => api.get(`/test-runs/${id}`),
  create: (data: any) => api.post('/test-runs/', data),
  update: (id: string, data: any) => api.patch(`/test-runs/${id}`, data),
  start: (id: string) => api.post(`/test-runs/${id}/start`),
  complete: (id: string) => api.post(`/test-runs/${id}/complete`),
  stats: () => api.get('/test-runs/stats'),
}

// --- Test Results ---
export const testResultsApi = {
  list: (params?: any) => api.get('/test-results/', { params }),
  get: (id: string) => api.get(`/test-results/${id}`),
  update: (id: string, data: any) => api.patch(`/test-results/${id}`, data),
  batch: (data: any[]) => api.post('/test-results/batch', data),
}

// --- Reports ---
export const reportsApi = {
  generate: (data: any) => api.post('/reports/generate', data),
  download: (filename: string) => api.get(`/reports/download/${filename}`, { responseType: 'blob' }),
  configs: () => api.get('/reports/configs'),
}

// --- Agents ---
export const agentsApi = {
  list: () => api.get('/agents/'),
  get: (id: string) => api.get(`/agents/${id}`),
  register: (data: any) => api.post('/agents/register', data),
  delete: (id: string) => api.delete(`/agents/${id}`),
}

// --- Whitelists ---
export const whitelistsApi = {
  list: () => api.get('/whitelists/'),
  get: (id: string) => api.get(`/whitelists/${id}`),
  create: (data: any) => api.post('/whitelists/', data),
  update: (id: string, data: any) => api.put(`/whitelists/${id}`, data),
  delete: (id: string) => api.delete(`/whitelists/${id}`),
  duplicate: (id: string) => api.post(`/whitelists/${id}/duplicate`),
}

// --- Discovery ---
export const discoveryApi = {
  scan: (data: any) => api.post('/discovery/scan', data),
  registerDevice: (data: any) => api.post('/discovery/register-device', data),
}

// --- Audit Logs ---
export const auditApi = {
  list: (params?: any) => api.get('/audit-logs/', { params }),
  complianceSummary: () => api.get('/audit-logs/compliance-summary'),
}

// --- Admin ---
export const adminApi = {
  dashboard: () => api.get('/admin/dashboard'),
  systemInfo: () => api.get('/admin/system-info'),
}

// --- Synopsis ---
export const synopsisApi = {
  generate: (data: any) => api.post('/synopsis/generate', data),
  approve: (data: any) => api.post('/synopsis/approve', data),
}
