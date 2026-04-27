import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import TestRunDetailPage from '@/pages/TestRunDetailPage'

const mockState = vi.hoisted(() => ({
  run: {} as Record<string, unknown>,
  results: [] as Record<string, unknown>[],
  reportGenerate: vi.fn().mockResolvedValue({ data: {} }),
  reportDownload: vi.fn().mockResolvedValue({ data: new Blob([]) }),
}))

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: vi.fn().mockReturnValue({
    user: { id: '1', username: 'admin', email: 'admin@test.com', full_name: 'Admin', role: 'admin', is_active: true },
    loading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}))

vi.mock('@/lib/api', () => ({
  testRunsApi: {
    get: vi.fn().mockImplementation(() => Promise.resolve({ data: mockState.run })),
    update: vi.fn(),
    start: vi.fn(),
    cancel: vi.fn(),
    pause: vi.fn(),
    pauseCable: vi.fn(),
    resume: vi.fn(),
    complete: vi.fn(),
    requestReview: vi.fn(),
  },
  testResultsApi: {
    list: vi.fn().mockImplementation(() => Promise.resolve({ data: mockState.results })),
    update: vi.fn(),
    override: vi.fn(),
  },
  reportsApi: {
    generate: mockState.reportGenerate,
    download: mockState.reportDownload,
  },
  profilesApi: { autoLearn: vi.fn() },
  getApiErrorMessage: vi.fn((_err: unknown, fallback: string) => fallback),
}))

vi.mock('@/hooks/useTestRunWebSocket', () => ({
  useTestRunWebSocket: vi.fn().mockReturnValue({
    messages: [],
    lastProgress: null,
    isConnected: false,
    hasConnectedOnce: false,
    isFresh: false,
    cableStatus: 'connected',
    terminalOutput: {},
    reconnectCount: 0,
    cableProbe: null,
  }),
}))

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/test-runs/run-1']}>
        <Routes>
          <Route path="/test-runs/:id" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('TestRunDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockState.reportGenerate.mockResolvedValue({ data: {} })
    mockState.reportDownload.mockResolvedValue({ data: new Blob([]) })
    mockState.results = []
    mockState.run = {
      id: 'run-1',
      device_id: 'dev-1',
      device_name: null,
      device_ip: '192.168.1.100',
      template_id: 'tpl-1',
      template_name: 'Full Security Scan',
      status: 'completed',
      overall_verdict: 'pass',
      progress_pct: 100,
      total_tests: 12,
      completed_tests: 12,
      passed_tests: 11,
      failed_tests: 0,
      advisory_tests: 1,
      na_tests: 0,
      run_metadata: {},
      started_at: '2026-01-01T10:00:00Z',
      completed_at: '2026-01-01T10:05:00Z',
      created_at: '2026-01-01T10:00:00Z',
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
        trust_tier_counts: { release_blocking: 4, review_required: 2, advisory: 3, manual_evidence: 3 },
        reasons: ['1 advisory finding should be called out in the report.'],
        next_step: 'Issue the report with the advisory notes and follow-up actions captured.',
        summary: 'Operational with advisories (9/10). 1 advisory finding should be called out in the report.',
      },
    }
  })

  it('renders without crashing and shows content', async () => {
    renderWithProviders(<TestRunDetailPage />)
    await waitFor(() => {
      const found =
        screen.queryByText(/Device dev-1/i) ||
        screen.queryByText(/Started/i) ||
        screen.queryByText(/Operational with advisories/i)
      expect(found).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  it('shows compact summary instead of a misleading time-left estimate', async () => {
    renderWithProviders(<TestRunDetailPage />)

    await waitFor(() => {
      expect(screen.getAllByText(/Operational with advisories \(9\/10\)/i).length).toBeGreaterThan(0)
    })

    expect(screen.queryByText(/left$/i)).not.toBeInTheDocument()
  })

  it('shows readiness summary when available', async () => {
    renderWithProviders(<TestRunDetailPage />)

    await waitFor(() => {
      expect(screen.getAllByText(/Operational with advisories \(9\/10\)/i).length).toBeGreaterThan(0)
    })

    expect(screen.getByText(/Report ready/i)).toBeInTheDocument()
  })

  it('shows loading state initially', () => {
    renderWithProviders(<TestRunDetailPage />)
    const spinner = document.querySelector('.animate-spin')
    expect(spinner).toBeInTheDocument()
  })

  it('shows persisted current test when websocket has not delivered a start event', async () => {
    mockState.run = {
      ...mockState.run,
      status: 'running',
      progress_pct: 25,
      completed_tests: 1,
      run_metadata: {
        current_test: {
          test_id: 'U35',
          test_name: 'Web Server Vulnerability Scan',
          status: 'running',
        },
      },
      readiness_summary: {
        ...(mockState.run.readiness_summary as Record<string, unknown>),
        level: 'in_progress',
        label: 'Run still in progress',
        report_ready: false,
        operational_ready: false,
        completed_result_count: 1,
        total_result_count: 4,
        summary: 'Run still in progress.',
      },
    }
    mockState.results = [
      {
        id: 'result-u01',
        test_id: 'U01',
        test_name: 'Connectivity Check',
        tier: 'automatic',
        verdict: 'pass',
        is_essential: 'yes',
      },
      {
        id: 'result-u35',
        test_id: 'U35',
        test_name: 'Web Server Vulnerability Scan',
        tier: 'automatic',
        verdict: 'pending',
        is_essential: 'yes',
      },
    ]

    renderWithProviders(<TestRunDetailPage />)

    expect(await screen.findByText(/Running: Web Server Vulnerability Scan/i)).toBeInTheDocument()
  })
})
