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
        screen.queryByText(/192\.168\.1\.100/i) ||
        screen.queryByText(/cam-lobby/i) ||
        screen.queryByText(/Full Security Scan/i) ||
        screen.queryByText(/completed/i)
      expect(found).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  it('shows loading state initially', () => {
    renderWithProviders(<TestRunDetailPage />)
    const spinner = document.querySelector('.animate-spin')
    expect(spinner).toBeInTheDocument()
  })
})
