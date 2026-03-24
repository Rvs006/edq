import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AuditLogPage from '@/pages/AuditLogPage'

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', username: 'admin', email: 'admin@electracom.co.uk', full_name: 'Admin User', role: 'admin', is_active: true },
    loading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}))

vi.mock('@/lib/api', () => ({
  auditApi: {
    list: vi.fn().mockResolvedValue({
      data: {
        items: [{ id: '1', user_id: '1', user_name: 'admin', action: 'login', resource_type: 'auth', resource_id: null, details: null, ip_address: '127.0.0.1', compliance_refs: null, created_at: '2026-01-01T00:00:00Z' }],
        total: 1, skip: 0, limit: 50,
      },
    }),
    complianceSummary: vi.fn().mockResolvedValue({ data: { total_events: 1, by_action: { login: 1 } } }),
    exportCsv: vi.fn(),
  },
  adminApi: { users: vi.fn().mockResolvedValue({ data: [] }) },
}))

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('AuditLogPage', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders the page title', () => {
    renderWithProviders(<AuditLogPage />)
    expect(screen.getByText('Audit Log')).toBeInTheDocument()
  })

  it('renders Export CSV button', () => {
    renderWithProviders(<AuditLogPage />)
    expect(screen.getByText('Export CSV')).toBeInTheDocument()
  })
})
