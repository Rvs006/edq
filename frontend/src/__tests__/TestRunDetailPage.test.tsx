import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import TestRunDetailPage from '@/pages/TestRunDetailPage'

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
    get: vi.fn().mockResolvedValue({
      data: {
        id: 'run-1',
        device_id: 'dev-1',
        template_id: 'tpl-1',
        status: 'completed',
        verdict: 'pass',
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
        device: { ip_address: '192.168.1.100', hostname: 'cam-lobby' },
        template: { name: 'Full Security Scan' },
      },
    }),
    getResults: vi.fn().mockResolvedValue({ data: [] }),
  },
  reportsApi: { generate: vi.fn() },
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
  })

  it('renders without crashing and shows content', async () => {
    renderWithProviders(<TestRunDetailPage />)
    await waitFor(() => {
      const found =
        screen.queryByText(/Device dev-1/i) ||
        screen.queryByText(/Started/i) ||
        screen.queryByText(/Quick guide:/i)
      expect(found).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  it('shows guidance instead of a misleading time-left estimate', async () => {
    renderWithProviders(<TestRunDetailPage />)

    await waitFor(() => {
      expect(screen.getByText(/Quick guide:/i)).toBeInTheDocument()
    })

    expect(screen.queryByText(/left$/i)).not.toBeInTheDocument()
  })

  it('shows readiness summary when available', async () => {
    renderWithProviders(<TestRunDetailPage />)

    await waitFor(() => {
      expect(screen.getByText(/Readiness: Operational with advisories \(9\/10\)/i)).toBeInTheDocument()
    })

    expect(screen.getByText(/Official report: ready/i)).toBeInTheDocument()
  })

  it('shows loading state initially', () => {
    renderWithProviders(<TestRunDetailPage />)
    const spinner = document.querySelector('.animate-spin')
    expect(spinner).toBeInTheDocument()
  })
})
