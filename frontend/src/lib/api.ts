import axios, { type AxiosResponse } from 'axios'
import type {
  Device, TestRun, TestResult, TestTemplate, TestLibraryItem,
  TestPlan, Whitelist, AuditLogEntry, PaginatedResponse, UserProfile,
} from './types'
import {
  normalizeTestResult,
  normalizeTestRun,
} from './testContracts'

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

// Endpoints that don't require CSRF (no session exists yet)
const CSRF_EXEMPT = ['/auth/login', '/auth/register', '/auth/refresh']
const AUTH_RETRY_EXEMPT = ['/auth/login', '/auth/register', '/auth/refresh']

type RetryableRequestConfig = {
  _retry?: boolean
  url?: string
  [key: string]: unknown
}

let refreshPromise: Promise<void> | null = null

function withNormalizedData<TInput, TOutput>(
  promise: Promise<AxiosResponse<TInput>>,
  normalizer: (data: TInput) => TOutput,
) {
  return promise.then((response) => ({
    ...response,
    data: normalizer(response.data),
  }))
}

async function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = api.post('/auth/refresh').then(() => undefined).finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

api.interceptors.request.use((config) => {
  if (config.method && ['post', 'put', 'patch', 'delete'].includes(config.method)) {
    const isExempt = CSRF_EXEMPT.some((path) => config.url?.endsWith(path))
    const csrf = getCsrfToken()
    if (csrf) {
      config.headers['X-CSRF-Token'] = csrf
    } else if (!isExempt) {
      return Promise.reject(new Error('CSRF token is missing. Please refresh the page and log in again.'))
    }
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status
    const originalRequest = (error.config || {}) as RetryableRequestConfig
    const requestUrl = String(originalRequest.url || '')

    if (
      status === 401
      && !originalRequest._retry
      && !AUTH_RETRY_EXEMPT.some((path) => requestUrl.endsWith(path))
    ) {
      originalRequest._retry = true
      try {
        await refreshSession()
        return api.request(originalRequest)
      } catch (refreshError) {
        const path = window.location.pathname
        if (path !== '/login' && path !== '/' && !requestUrl.includes('/auth/me')) {
          window.location.href = '/login'
        }
        return Promise.reject(refreshError)
      }
    }

    if (status === 401) {
      const path = window.location.pathname
      if (path !== '/login' && path !== '/' && !requestUrl.includes('/auth/me')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api

export const authApi = {
  login: (data: { username: string; password: string; totp_code?: string }) => api.post('/auth/login', data),
  register: (data: { username: string; email: string; password: string; full_name?: string }) => api.post('/auth/register', data),
  logout: () => api.post('/auth/logout'),
  refresh: () => api.post('/auth/refresh'),
  me: () => api.get<UserProfile>('/auth/me'),
  updateProfile: (data: { full_name?: string; email?: string }) => api.patch<UserProfile>('/auth/me', data),
  changePassword: (data: { current_password: string; new_password: string }) => api.post('/auth/change-password', data),
  // Two-Factor Authentication
  twoFactorStatus: () => api.get('/auth/2fa/status'),
  twoFactorSetup: () => api.post('/auth/2fa/setup'),
  twoFactorVerify: (code: string) => api.post('/auth/2fa/verify', { code }),
  twoFactorDisable: (code: string, password: string) => api.post('/auth/2fa/disable', { code, password }),
  // OIDC / SSO
  oidcConfig: () => api.get('/auth/oidc/config'),
  oidcCallback: (data: { code: string; redirect_uri: string; nonce: string; provider?: string; code_verifier?: string }) => api.post('/auth/oidc/callback', data),
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
  create: (data: Record<string, unknown>) => api.post('/device-profiles/', data),
  update: (id: string, data: Record<string, unknown>) => api.patch(`/device-profiles/${id}`, data),
  delete: (id: string) => api.delete(`/device-profiles/${id}`),
  autoLearn: (testRunId: string) => api.post('/device-profiles/auto-learn', { test_run_id: testRunId }),
}

export const templatesApi = {
  list: (params?: { limit?: number }) => api.get<TestTemplate[]>('/test-templates/', { params }),
  get: (id: string) => api.get<TestTemplate>(`/test-templates/${id}`),
  create: (data: { name: string; description?: string; test_ids: string[]; device_category?: string }) => api.post<TestTemplate>('/test-templates/', data),
  update: (id: string, data: { name?: string; description?: string; test_ids?: string[]; device_category?: string; is_default?: boolean }) => api.patch<TestTemplate>(`/test-templates/${id}`, data),
  delete: (id: string) => api.delete(`/test-templates/${id}`),
  library: () => api.get<TestLibraryItem[]>('/test-templates/library'),
}

export const testRunsApi = {
  list: (params?: { status?: string; device_id?: string; skip?: number; limit?: number }) =>
    withNormalizedData(api.get<Record<string, unknown>[]>('/test-runs/', { params }), (data) => data.map(normalizeTestRun)),
  get: (id: string) =>
    withNormalizedData(api.get<Record<string, unknown>>(`/test-runs/${id}`), normalizeTestRun),
  create: (data: { device_id: string; plan_id?: string; template_id?: string }) =>
    withNormalizedData(api.post<Record<string, unknown>>('/test-runs/', data), normalizeTestRun),
  update: (id: string, data: { connection_scenario?: string; synopsis?: string; synopsis_status?: string }) =>
    withNormalizedData(api.patch<Record<string, unknown>>(`/test-runs/${id}`, data), normalizeTestRun),
  start: (id: string) => api.post(`/test-runs/${id}/start`),
  cancel: (id: string) => api.post(`/test-runs/${id}/cancel`),
  pause: (id: string) => api.post(`/test-runs/${id}/pause`),
  pauseCable: (id: string) => api.post(`/test-runs/${id}/pause-cable`),
  resume: (id: string) => api.post(`/test-runs/${id}/resume`),
  requestReview: (id: string) =>
    withNormalizedData(api.post<Record<string, unknown>>(`/test-runs/${id}/request-review`), normalizeTestRun),
  complete: (id: string) =>
    withNormalizedData(api.post<Record<string, unknown>>(`/test-runs/${id}/complete`), normalizeTestRun),
  checkDuplicate: (deviceId: string, templateId: string) => api.get<{ has_duplicates: boolean; count: number; existing_runs: { id: string; status: string; overall_verdict: string | null; completed_tests: number; total_tests: number; confidence: number; created_at: string; completed_at: string | null }[] }>('/test-runs/check-duplicate', { params: { device_id: deviceId, template_id: templateId } }),
  stats: () => api.get<{ total: number; by_status: Record<string, number>; by_verdict?: Record<string, number>; completed_this_week?: number }>('/test-runs/stats'),
}

export const testResultsApi = {
  list: (params?: { test_run_id?: string; skip?: number; limit?: number }) =>
    withNormalizedData(api.get<Record<string, unknown>[]>('/test-results/', { params }), (data) => data.map(normalizeTestResult)),
  get: (id: string) =>
    withNormalizedData(api.get<Record<string, unknown>>(`/test-results/${id}`), normalizeTestResult),
  update: (id: string, data: { verdict?: string; comment?: string; findings?: unknown; raw_output?: string; engineer_notes?: string }) =>
    withNormalizedData(api.patch<Record<string, unknown>>(`/test-results/${id}`, data), normalizeTestResult),
  override: (id: string, data: { verdict: string; comment?: string; override_reason: string }) =>
    withNormalizedData(api.post<Record<string, unknown>>(`/test-results/${id}/override`, data), normalizeTestResult),
}

export const reportsApi = {
  generate: (data: { test_run_id: string; report_type?: string; format?: string; template_id?: string; template_key?: string; include_synopsis?: boolean }) => api.post('/reports/generate', data),
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
  users: (params?: { skip?: number; limit?: number }) => api.get<UserProfile[]>('/users/', { params }),
  updateUser: (id: string, data: { role?: string; is_active?: boolean; full_name?: string; email?: string }) => api.patch(`/users/${id}`, data),
}

export const synopsisApi = {
  generate: (data: { test_run_id: string; prompt?: string }) => api.post('/synopsis/generate', data),
  approve: (data: { synopsis_id: string }) => api.post('/synopsis/approve', data),
}

export const networkScanApi = {
  list: (params?: { skip?: number; limit?: number }) => api.get('/network-scan/', { params }),
  detectNetworks: () => api.get('/network-scan/detect-networks'),
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
  systemStatus: () => api.get<{
    status: string
    checked_at: string
    backend: { status: string }
    database: { status: string }
    tools_sidecar: { status: string }
    tools: Record<string, string>
  }>('/health/system-status'),
}

export const cveApi = {
  lookup: (data: { keyword?: string; device_id?: string; max_results?: number }) =>
    api.post('/cve/lookup', data),
}

export const agentsApi = {
  list: () => api.get('/agents/'),
  get: (id: string) => api.get(`/agents/${id}`),
}

export const scanSchedulesApi = {
  list: (params?: { device_id?: string; is_active?: boolean; skip?: number; limit?: number }) =>
    api.get('/scan-schedules/', { params }),
  get: (id: string) => api.get(`/scan-schedules/${id}`),
  create: (data: { device_id: string; template_id: string; frequency: string; max_runs?: number }) =>
    api.post('/scan-schedules/', data),
  update: (id: string, data: { frequency?: string; is_active?: boolean; max_runs?: number }) =>
    api.patch(`/scan-schedules/${id}`, data),
  delete: (id: string) => api.delete(`/scan-schedules/${id}`),
  diff: (id: string) => api.get(`/scan-schedules/${id}/diff`),
}

export const authorizedNetworksApi = {
  list: (params?: { active_only?: boolean; skip?: number; limit?: number }) =>
    api.get('/authorized-networks/', { params }),
  get: (id: string) => api.get(`/authorized-networks/${id}`),
  create: (data: { cidr: string; label?: string; description?: string }) =>
    api.post('/authorized-networks/', data),
  update: (id: string, data: { label?: string; description?: string; is_active?: boolean }) =>
    api.patch(`/authorized-networks/${id}`, data),
  delete: (id: string) => api.delete(`/authorized-networks/${id}`),
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

export function getApiErrorMessage(err: unknown, fallback = 'An error occurred'): string {
  const axiosErr = err as { response?: { data?: { detail?: string } } }
  return axiosErr?.response?.data?.detail || fallback
}
