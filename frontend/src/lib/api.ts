import axios from 'axios'
import type {
  Device, TestRun, TestResult, TestTemplate, TestLibraryItem,
  TestPlan, Whitelist, AuditLogEntry, PaginatedResponse, UserProfile,
} from './types'

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
  register: (data: { username: string; email: string; password: string; full_name?: string }) => api.post('/auth/register', data),
  logout: () => api.post('/auth/logout'),
  me: () => api.get<UserProfile>('/auth/me'),
  changePassword: (data: { current_password: string; new_password: string }) => api.post('/auth/change-password', data),
}

export const devicesApi = {
  list: (params?: { category?: string; status?: string; search?: string; skip?: number; limit?: number }) => api.get<Device[]>('/devices/', { params }),
  get: (id: string) => api.get<Device>(`/devices/${id}`),
  create: (data: { ip_address: string; mac_address?: string; hostname?: string; manufacturer?: string; model?: string; category?: string; notes?: string }) => api.post<Device>('/devices/', data),
  update: (id: string, data: Partial<Device>) => api.patch<Device>(`/devices/${id}`, data),
  delete: (id: string) => api.delete(`/devices/${id}`),
  stats: () => api.get<{ total: number; by_status: Record<string, number>; by_category: Record<string, number> }>('/devices/stats'),
}

export const profilesApi = {
  list: (params?: { skip?: number; limit?: number }) => api.get('/device-profiles/', { params }),
  get: (id: string) => api.get(`/device-profiles/${id}`),
  create: (data: { name: string; manufacturer?: string; model?: string; category?: string }) => api.post('/device-profiles/', data),
  update: (id: string, data: { name?: string; manufacturer?: string; model?: string; category?: string }) => api.patch(`/device-profiles/${id}`, data),
  delete: (id: string) => api.delete(`/device-profiles/${id}`),
}

export const templatesApi = {
  list: () => api.get<TestTemplate[]>('/test-templates/'),
  get: (id: string) => api.get<TestTemplate>(`/test-templates/${id}`),
  create: (data: { name: string; description?: string; test_ids: string[]; device_category?: string }) => api.post<TestTemplate>('/test-templates/', data),
  update: (id: string, data: { name?: string; description?: string; test_ids?: string[]; device_category?: string; is_default?: boolean }) => api.patch<TestTemplate>(`/test-templates/${id}`, data),
  delete: (id: string) => api.delete(`/test-templates/${id}`),
  library: () => api.get<TestLibraryItem[]>('/test-templates/library'),
}

export const testRunsApi = {
  list: (params?: { status?: string; device_id?: string; skip?: number; limit?: number }) => api.get<TestRun[]>('/test-runs/', { params }),
  get: (id: string) => api.get<TestRun>(`/test-runs/${id}`),
  create: (data: { device_id: string; plan_id?: string; template_id?: string }) => api.post<TestRun>('/test-runs/', data),
  update: (id: string, data: Partial<TestRun>) => api.patch<TestRun>(`/test-runs/${id}`, data),
  start: (id: string) => api.post(`/test-runs/${id}/start`),
  complete: (id: string) => api.post(`/test-runs/${id}/complete`),
  stats: () => api.get<{ total: number; by_status: Record<string, number> }>('/test-runs/stats'),
}

export const testResultsApi = {
  list: (params?: { test_run_id?: string; skip?: number; limit?: number }) => api.get<TestResult[]>('/test-results/', { params }),
  get: (id: string) => api.get<TestResult>(`/test-results/${id}`),
  update: (id: string, data: { verdict?: string; comment?: string; findings?: string; raw_output?: string; tier?: string }) => api.patch<TestResult>(`/test-results/${id}`, data),
  override: (id: string, data: { verdict: string; comment: string }) => api.post(`/test-results/${id}/override`, data),
  batch: (data: { id: string; verdict?: string; comment?: string }[]) => api.post('/test-results/batch', data),
}

export const reportsApi = {
  generate: (data: { test_run_id: string; format?: string; template_id?: string }) => api.post('/reports/generate', data),
  download: (filename: string) => api.get(`/reports/download/${filename}`, { responseType: 'blob' }),
  configs: () => api.get('/reports/configs'),
  templates: () => api.get('/reports/templates'),
}

export const whitelistsApi = {
  list: () => api.get<Whitelist[]>('/whitelists/'),
  get: (id: string) => api.get<Whitelist>(`/whitelists/${id}`),
  create: (data: { name: string; description?: string; entries: { port: number; protocol: string; service: string; required_version?: string }[]; is_default?: boolean }) => api.post<Whitelist>('/whitelists/', data),
  update: (id: string, data: { name?: string; description?: string; entries?: { port: number; protocol: string; service: string; required_version?: string }[]; is_default?: boolean }) => api.put<Whitelist>(`/whitelists/${id}`, data),
  delete: (id: string) => api.delete(`/whitelists/${id}`),
  duplicate: (id: string) => api.post<Whitelist>(`/whitelists/${id}/duplicate`),
}

export const discoveryApi = {
  scan: (data: { subnet?: string; ip_address?: string; interface?: string }) => api.post('/discovery/scan', data),
  registerDevice: (data: { ip_address: string; mac_address?: string; hostname?: string }) => api.post('/discovery/register-device', data),
}

export const auditApi = {
  list: (params?: { action?: string; resource_type?: string; user_id?: string; date_from?: string; date_to?: string; skip?: number; limit?: number }) => api.get<PaginatedResponse<AuditLogEntry>>('/audit-logs/', { params }),
  complianceSummary: () => api.get('/audit-logs/compliance-summary'),
  exportCsv: (params?: { action?: string; resource_type?: string; user_id?: string; date_from?: string; date_to?: string }) => api.get('/audit-logs/export', { params, responseType: 'blob' }),
}

export const adminApi = {
  dashboard: () => api.get('/admin/dashboard'),
  systemInfo: () => api.get('/admin/system-info'),
  users: (params?: { skip?: number; limit?: number }) => api.get<UserProfile[]>('/admin/users', { params }),
  updateUser: (id: string, data: { role?: string; is_active?: boolean; full_name?: string; email?: string }) => api.put(`/admin/users/${id}`, data),
}

export const synopsisApi = {
  generate: (data: { test_run_id: string; prompt?: string }) => api.post('/synopsis/generate', data),
  approve: (data: { synopsis_id: string }) => api.post('/synopsis/approve', data),
}

export const networkScanApi = {
  list: (params?: { skip?: number; limit?: number }) => api.get('/network-scan/', { params }),
  discover: (data: { cidr: string; connection_scenario: string; test_ids: string[] }) => api.post('/network-scan/discover', data),
  start: (data: { scan_id: string; device_ips: string[]; test_ids: string[]; connection_scenario: string }) => api.post('/network-scan/start', data),
  get: (id: string) => api.get(`/network-scan/${id}`),
  results: (id: string) => api.get(`/network-scan/${id}/results`),
}

export const testPlansApi = {
  list: (params?: { skip?: number; limit?: number }) => api.get<TestPlan[]>('/test-plans/', { params }),
  get: (id: string) => api.get<TestPlan>(`/test-plans/${id}`),
  create: (data: { name: string; description?: string | null; base_template_id?: string | null; test_configs: { test_id: string; enabled: boolean; tier_override: string | null; custom?: { name: string; description: string; tier: string } | null }[] }) => api.post<TestPlan>('/test-plans/', data),
  update: (id: string, data: { name?: string; description?: string | null; test_configs?: { test_id: string; enabled: boolean; tier_override: string | null; custom?: { name: string; description: string; tier: string } | null }[] }) => api.put<TestPlan>(`/test-plans/${id}`, data),
  delete: (id: string) => api.delete(`/test-plans/${id}`),
  clone: (id: string) => api.post<TestPlan>(`/test-plans/${id}/clone`),
}

export const healthApi = {
  check: () => api.get('/health'),
  toolVersions: () => api.get<{ tools: Record<string, string> }>('/health/tools/versions'),
}
