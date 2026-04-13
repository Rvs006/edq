import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

let requestInterceptor: ((config: Record<string, unknown>) => Record<string, unknown> | Promise<Record<string, unknown>>) | undefined
let responseErrorInterceptor: ((error: { response?: { status?: number }; config?: Record<string, unknown> }) => Promise<unknown>) | undefined

const mockAxios = {
  create: vi.fn(),
  interceptors: {
    request: {
      use: vi.fn((handler: typeof requestInterceptor) => {
        requestInterceptor = handler
      }),
    },
    response: {
      use: vi.fn((_: unknown, errorHandler: typeof responseErrorInterceptor) => {
        responseErrorInterceptor = errorHandler
      }),
    },
  },
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  request: vi.fn(),
}

mockAxios.create.mockImplementation(() => mockAxios)

vi.mock('edq-http', () => ({ default: mockAxios }))

describe('API module', () => {
  let apiModule: Awaited<typeof import('@/lib/api')>

  beforeAll(async () => {
    apiModule = await import('@/lib/api')
  })

  beforeEach(() => {
    vi.clearAllMocks()
    document.cookie = 'edq_csrf=test-csrf'
  })

  it('exports all expected API namespaces', () => {
    expect(apiModule.authApi).toBeDefined()
    expect(apiModule.devicesApi).toBeDefined()
    expect(apiModule.profilesApi).toBeDefined()
    expect(apiModule.templatesApi).toBeDefined()
    expect(apiModule.testRunsApi).toBeDefined()
    expect(apiModule.testResultsApi).toBeDefined()
    expect(apiModule.reportsApi).toBeDefined()
    expect(apiModule.whitelistsApi).toBeDefined()
    expect(apiModule.discoveryApi).toBeDefined()
    expect(apiModule.auditApi).toBeDefined()
    expect(apiModule.adminApi).toBeDefined()
    expect(apiModule.synopsisApi).toBeDefined()
    expect(apiModule.networkScanApi).toBeDefined()
    expect(apiModule.testPlansApi).toBeDefined()
    expect(apiModule.healthApi).toBeDefined()
  })

  it('authApi has login, register, logout, me, changePassword methods', () => {
    const { authApi } = apiModule

    expect(typeof authApi.login).toBe('function')
    expect(typeof authApi.register).toBe('function')
    expect(typeof authApi.logout).toBe('function')
    expect(typeof authApi.refresh).toBe('function')
    expect(typeof authApi.me).toBe('function')
    expect(typeof authApi.changePassword).toBe('function')
  })

  it('devicesApi has CRUD methods plus stats', () => {
    const { devicesApi } = apiModule

    expect(typeof devicesApi.list).toBe('function')
    expect(typeof devicesApi.get).toBe('function')
    expect(typeof devicesApi.create).toBe('function')
    expect(typeof devicesApi.update).toBe('function')
    expect(typeof devicesApi.delete).toBe('function')
    expect(typeof devicesApi.stats).toBe('function')
  })

  it('healthApi exposes the health status methods', () => {
    const { healthApi } = apiModule

    expect(typeof healthApi.check).toBe('function')
    expect(typeof healthApi.toolVersions).toBe('function')
    expect(typeof healthApi.systemStatus).toBe('function')
  })

  it('normalizes test run responses returned through the API wrapper', async () => {
    const { testRunsApi } = apiModule
    mockAxios.get.mockResolvedValueOnce({
      data: {
        id: 'run-1',
        device_id: 'device-1',
        user_id: 'engineer-1',
        user_name: 'Engineer One',
        status: 'complete',
        created_at: '2026-04-01T00:00:00Z',
      },
    })

    const response = await testRunsApi.get('run-1')

    expect(response.data.engineer_id).toBe('engineer-1')
    expect(response.data.engineer_name).toBe('Engineer One')
    expect(response.data.status).toBe('completed')
  })

  it('normalizes awaiting-review test run status through the API wrapper', async () => {
    const { testRunsApi } = apiModule
    mockAxios.get.mockResolvedValueOnce({
      data: {
        id: 'run-2',
        device_id: 'device-1',
        engineer_id: 'engineer-1',
        status: 'awaiting_review',
        created_at: '2026-04-01T00:00:00Z',
      },
    })

    const response = await testRunsApi.get('run-2')

    expect(response.data.status).toBe('awaiting_review')
  })

  it('normalizes readiness summary on test run responses', async () => {
    const { testRunsApi } = apiModule
    mockAxios.get.mockResolvedValueOnce({
      data: {
        id: 'run-3',
        device_id: 'device-1',
        engineer_id: 'engineer-1',
        status: 'completed',
        confidence: 9,
        readiness_summary: {
          score: 9,
          level: 'conditional',
          label: 'Operational with advisories',
          report_ready: true,
          operational_ready: false,
          blocking_issue_count: 0,
          pending_manual_count: 0,
          release_blocking_failure_count: 0,
          review_required_issue_count: 0,
          manual_evidence_pending_count: 0,
          advisory_count: 1,
          override_count: 0,
          failed_test_count: 0,
          completed_result_count: 12,
          total_result_count: 12,
          trust_tier_counts: { release_blocking: 4, review_required: 2 },
          reasons: ['1 advisory finding should be called out in the report.'],
          next_step: 'Issue the report with the advisory notes and follow-up actions captured.',
          summary: 'Operational with advisories (9/10). 1 advisory finding should be called out in the report.',
        },
        created_at: '2026-04-01T00:00:00Z',
      },
    })

    const response = await testRunsApi.get('run-3')

    expect(response.data.readiness_summary?.score).toBe(9)
    expect(response.data.readiness_summary?.report_ready).toBe(true)
    expect(response.data.readiness_summary?.reasons[0]).toMatch(/advisory finding/i)
  })

  it('normalizes test result responses returned through the API wrapper', async () => {
    const { testResultsApi } = apiModule
    mockAxios.get.mockResolvedValueOnce({
      data: {
        id: 'result-1',
        test_run_id: 'run-1',
        test_number: 'U01',
        test_name: 'Ping',
        tool_used: 'ping',
        raw_stdout: 'output',
        parsed_findings: { reachable: true },
        created_at: '2026-04-01T00:00:00Z',
      },
    })

    const response = await testResultsApi.get('result-1')

    expect(response.data.test_id).toBe('U01')
    expect(response.data.tool).toBe('ping')
    expect(response.data.raw_output).toBe('output')
    expect(response.data.findings).toEqual({ reachable: true })
  })

  it('refreshes once and retries the original request after a 401', async () => {
    mockAxios.post.mockResolvedValueOnce({ data: { message: 'Token refreshed' } })
    mockAxios.request.mockResolvedValueOnce({ data: { ok: true } })

    const response = await responseErrorInterceptor?.({
      response: { status: 401 },
      config: { url: '/devices/', headers: {} },
    })

    expect(mockAxios.post).toHaveBeenCalledWith('/auth/refresh')
    expect(mockAxios.request).toHaveBeenCalledWith(
      expect.objectContaining({
        url: '/devices/',
        _retry: true,
      }),
    )
    expect(response).toEqual({ data: { ok: true } })
  })
})
