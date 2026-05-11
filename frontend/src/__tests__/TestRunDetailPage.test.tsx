import { describe, it, expect, vi, beforeEach, afterEach, beforeAll } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

let TestRunDetailPage: typeof import('@/pages/TestRunDetailPage').default

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
    bulkUpdateManual: vi.fn(),
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

vi.mock('framer-motion', async () => {
  const React = await import('react')
  const motionComponent = (tag: string) =>
    React.forwardRef<HTMLElement, any>(
      ({ children, initial, animate, exit, transition, ...props }, ref) =>
        React.createElement(tag, { ...props, ref }, children)
    )

  return {
    AnimatePresence: ({ children }: { children?: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    motion: new Proxy({}, {
      get: (_target, tag) => motionComponent(String(tag)),
    }),
  }
})

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

const queryClients: QueryClient[] = []

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  })
  queryClients.push(queryClient)
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
  beforeAll(async () => {
    TestRunDetailPage = (await import('@/pages/TestRunDetailPage')).default
  })

  afterEach(() => {
    queryClients.splice(0).forEach((client) => client.clear())
  })

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
          test_name: 'Web Server and HTTP Header Assessment',
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
        test_name: 'Web Server and HTTP Header Assessment',
        tier: 'automatic',
        verdict: 'pending',
        is_essential: 'yes',
      },
    ]

    renderWithProviders(<TestRunDetailPage />)

    expect(await screen.findByText(/Running: Web Server and HTTP Header Assessment/i)).toBeInTheDocument()
  })

  it('shows bulk manual controls for multiple pending manual tests', async () => {
    mockState.run = {
      ...mockState.run,
      status: 'awaiting_manual',
      overall_verdict: null,
      progress_pct: 50,
      completed_tests: 1,
      total_tests: 3,
      readiness_summary: {
        ...(mockState.run.readiness_summary as Record<string, unknown>),
        level: 'awaiting_manual_evidence',
        label: 'Manual evidence required',
        report_ready: false,
        operational_ready: false,
        pending_manual_count: 2,
        manual_evidence_pending_count: 2,
        completed_result_count: 1,
        total_result_count: 3,
        summary: 'Manual evidence required.',
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
        id: 'result-u20',
        test_id: 'U20',
        test_name: 'Network Disconnection Behaviour',
        tier: 'guided_manual',
        verdict: 'pending',
        is_essential: 'no',
      },
      {
        id: 'result-u21',
        test_id: 'U21',
        test_name: 'Web Interface Password Change',
        tier: 'guided_manual',
        verdict: 'pending',
        is_essential: 'yes',
      },
    ]

    renderWithProviders(<TestRunDetailPage />)

    expect(await screen.findByText(/Bulk manual result/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Select all$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Deselect all$/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/Bulk manual comments/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^Select all$/i }))
    expect(screen.getByRole('button', { name: /Apply/i })).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/Bulk manual comments/i), {
      target: { value: 'Observed on the device and marked not applicable.' },
    })

    expect(screen.getByRole('button', { name: /Apply/i })).not.toBeDisabled()
  })
})
