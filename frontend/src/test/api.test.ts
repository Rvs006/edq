import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock axios before importing api module
vi.mock('axios', () => {
  const mockAxios = {
    create: vi.fn(() => mockAxios),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  }
  return { default: mockAxios }
})

describe('API module', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('exports all expected API namespaces', async () => {
    const api = await import('@/lib/api')

    expect(api.authApi).toBeDefined()
    expect(api.devicesApi).toBeDefined()
    expect(api.profilesApi).toBeDefined()
    expect(api.templatesApi).toBeDefined()
    expect(api.testRunsApi).toBeDefined()
    expect(api.testResultsApi).toBeDefined()
    expect(api.reportsApi).toBeDefined()
    expect(api.whitelistsApi).toBeDefined()
    expect(api.discoveryApi).toBeDefined()
    expect(api.auditApi).toBeDefined()
    expect(api.adminApi).toBeDefined()
    expect(api.synopsisApi).toBeDefined()
    expect(api.networkScanApi).toBeDefined()
    expect(api.testPlansApi).toBeDefined()
    expect(api.healthApi).toBeDefined()
  })

  it('authApi has login, register, logout, me, changePassword methods', async () => {
    const { authApi } = await import('@/lib/api')

    expect(typeof authApi.login).toBe('function')
    expect(typeof authApi.register).toBe('function')
    expect(typeof authApi.logout).toBe('function')
    expect(typeof authApi.me).toBe('function')
    expect(typeof authApi.changePassword).toBe('function')
  })

  it('devicesApi has CRUD methods plus stats', async () => {
    const { devicesApi } = await import('@/lib/api')

    expect(typeof devicesApi.list).toBe('function')
    expect(typeof devicesApi.get).toBe('function')
    expect(typeof devicesApi.create).toBe('function')
    expect(typeof devicesApi.update).toBe('function')
    expect(typeof devicesApi.delete).toBe('function')
    expect(typeof devicesApi.stats).toBe('function')
  })

  it('healthApi has check and toolVersions methods', async () => {
    const { healthApi } = await import('@/lib/api')

    expect(typeof healthApi.check).toBe('function')
    expect(typeof healthApi.toolVersions).toBe('function')
  })
})
