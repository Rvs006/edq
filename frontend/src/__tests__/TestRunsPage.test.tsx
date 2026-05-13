import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import TestRunsPage from '@/pages/TestRunsPage'
import type { TestRun } from '@/lib/types'

const { mockTestRunsApi } = vi.hoisted(() => ({
  mockTestRunsApi: {
    list: vi.fn(),
    start: vi.fn(),
    checkDuplicate: vi.fn(),
    create: vi.fn(),
  },
}))

vi.mock('@/lib/api', () => ({
  testRunsApi: mockTestRunsApi,
  devicesApi: { list: vi.fn().mockResolvedValue({ data: [] }) },
  templatesApi: { list: vi.fn().mockResolvedValue({ data: [] }) },
  getApiErrorMessage: vi.fn((_err: unknown, fallback: string) => fallback),
}))

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

function renderWithProviders() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <TestRunsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('TestRunsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('groups test runs by device and normalizes template names', async () => {
    const runs = [
      {
        id: 'run-old',
        device_id: 'device-1',
        device_name: null,
        device_ip: '192.168.4.64',
        device_manufacturer: 'FixtureCo',
        device_model: 'FX-100',
        device_category: 'controller',
        template_name: 'Universal (Smart Profiling)',
        status: 'completed',
        overall_verdict: 'pass',
        completed_tests: 49,
        total_tests: 49,
        created_at: '2026-05-10T10:00:00Z',
        started_at: '2026-05-10T10:00:00Z',
      },
      {
        id: 'run-new',
        device_id: 'device-1',
        device_name: null,
        device_ip: '192.168.4.64',
        device_manufacturer: 'FixtureCo',
        device_model: 'FX-100',
        device_category: 'controller',
        template_name: 'Extended Qualification (Dylan Template)',
        status: 'completed',
        overall_verdict: 'pass',
        completed_tests: 49,
        total_tests: 49,
        created_at: '2026-05-12T10:00:00Z',
        started_at: '2026-05-12T10:00:00Z',
      },
    ] as TestRun[]
    mockTestRunsApi.list.mockResolvedValue({ data: runs })

    renderWithProviders()

    expect(await screen.findByText('FixtureCo FX-100')).toBeInTheDocument()
    expect(screen.getByText('2 runs')).toBeInTheDocument()
    expect(screen.getByText(/Latest/i)).toBeInTheDocument()
    expect(screen.getByText('Full Security Assessment')).toBeInTheDocument()
    expect(screen.getByText('Extended Qualification')).toBeInTheDocument()
  })
})
