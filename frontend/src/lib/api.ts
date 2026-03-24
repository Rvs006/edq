import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

function getCsrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)edq_csrf=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : null
}

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

api.interceptors.request.use((config) => {
  if (config.method && ['post', 'put', 'patch', 'delete'].includes(config.method)) {
    const csrf = getCsrfToken()
    if (csrf) {
      config.headers['X-CSRF-Token'] = csrf
    }
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const path = window.location.pathname
      if (path !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api

export const authApi = {
  login: (data: { username: string; password: string }) => api.post('/auth/login', data),
  register: (data: any) => api.post('/auth/register', data),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
  changePassword: (data: any) => api.post('/auth/change-password', data),
}

export const devicesApi = {
  list: (params?: any) => api.get('/devices/', { params }),
  get: (id: string) => api.get(`/devices/${id}`),
  create: (data: any) => api.post('/devices/', data),
  update: (id: string, data: any) => api.patch(`/devices/${id}`, data),
  delete: (id: string) => api.delete(`/devices/${id}`),
  stats: () => api.get('/devices/stats'),
}

export const profilesApi = {
  list: (params?: any) => api.get('/device-profiles/', { params }),
  get: (id: string) => api.get(`/device-profiles/${id}`),
  create: (data: any) => api.post('/device-profiles/', data),
  update: (id: string, data: any) => api.patch(`/device-profiles/${id}`, data),
  delete: (id: string) => api.delete(`/device-profiles/${id}`),
}

export const templatesApi = {
  list: () => api.get('/test-templates/'),
  get: (id: string) => api.get(`/test-templates/${id}`),
  create: (data: any) => api.post('/test-templates/', data),
  update: (id: string, data: any) => api.patch(`/test-templates/${id}`, data),
  delete: (id: string) => api.delete(`/test-templates/${id}`),
  library: () => api.get('/test-templates/library'),
}

export const testRunsApi = {
  list: (params?: any) => api.get('/test-runs/', { params }),
  get: (id: string) => api.get(`/test-runs/${id}`),
  create: (data: any) => api.post('/test-runs/', data),
  update: (id: string, data: any) => api.patch(`/test-runs/${id}`, data),
  start: (id: string) => api.post(`/test-runs/${id}/start`),
  complete: (id: string) => api.post(`/test-runs/${id}/complete`),
  stats: () => api.get('/test-runs/stats'),
}

export const testResultsApi = {
  list: (params?: any) => api.get('/test-results/', { params }),
  get: (id: string) => api.get(`/test-results/${id}`),
  update: (id: string, data: any) => api.patch(`/test-results/${id}`, data),
  override: (id: string, data: any) => api.post(`/test-results/${id}/override`, data),
  batch: (data: any[]) => api.post('/test-results/batch', data),
}

export const reportsApi = {
  generate: (data: any) => api.post('/reports/generate', data),
  download: (filename: string) => api.get(`/reports/download/${filename}`, { responseType: 'blob' }),
  configs: () => api.get('/reports/configs'),
  templates: () => api.get('/reports/templates'),
}

export const whitelistsApi = {
  list: () => api.get('/whitelists/'),
  get: (id: string) => api.get(`/whitelists/${id}`),
  create: (data: any) => api.post('/whitelists/', data),
  update: (id: string, data: any) => api.put(`/whitelists/${id}`, data),
  delete: (id: string) => api.delete(`/whitelists/${id}`),
  duplicate: (id: string) => api.post(`/whitelists/${id}/duplicate`),
}

export const discoveryApi = {
  scan: (data: any) => api.post('/discovery/scan', data),
  registerDevice: (data: any) => api.post('/discovery/register-device', data),
}

export const auditApi = {
  list: (params?: any) => api.get('/audit-logs/', { params }),
  complianceSummary: () => api.get('/audit-logs/compliance-summary'),
}

export const adminApi = {
  dashboard: () => api.get('/admin/dashboard'),
  systemInfo: () => api.get('/admin/system-info'),
  users: (params?: any) => api.get('/admin/users', { params }),
  updateUser: (id: string, data: any) => api.put(`/admin/users/${id}`, data),
}

export const synopsisApi = {
  generate: (data: any) => api.post('/synopsis/generate', data),
  approve: (data: any) => api.post('/synopsis/approve', data),
}

export const networkScanApi = {
  list: (params?: any) => api.get('/network-scan/', { params }),
  discover: (data: any) => api.post('/network-scan/discover', data),
  start: (data: any) => api.post('/network-scan/start', data),
  get: (id: string) => api.get(`/network-scan/${id}`),
  results: (id: string) => api.get(`/network-scan/${id}/results`),
}

export const testPlansApi = {
  list: (params?: any) => api.get('/test-plans/', { params }),
  get: (id: string) => api.get(`/test-plans/${id}`),
  create: (data: any) => api.post('/test-plans/', data),
  update: (id: string, data: any) => api.put(`/test-plans/${id}`, data),
  delete: (id: string) => api.delete(`/test-plans/${id}`),
  clone: (id: string) => api.post(`/test-plans/${id}/clone`),
}

export const healthApi = {
  check: () => api.get('/health'),
  toolVersions: () => api.get('/health/tools/versions'),
}

export const cveApi = {
  lookup: (data: { keyword?: string; device_id?: string; max_results?: number }) =>
    api.post('/cve/lookup', data),
}

export const brandingApi = {
  get: () => api.get('/settings/branding'),
  update: (data: { company_name?: string; primary_color?: string; footer_text?: string }) =>
    api.put('/settings/branding', data),
  uploadLogo: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/settings/branding/logo', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}
