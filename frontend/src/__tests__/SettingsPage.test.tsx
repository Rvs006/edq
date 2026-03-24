import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import SettingsPage from '@/pages/SettingsPage'

// Mock AuthContext
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: '1',
      username: 'admin',
      email: 'admin@electracom.co.uk',
      full_name: 'Admin User',
      role: 'admin',
      is_active: true,
    },
    loading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}))

vi.mock('@/lib/api', () => ({
  authApi: {
    me: vi.fn().mockResolvedValue({
      data: { id: '1', username: 'admin', email: 'admin@electracom.co.uk', full_name: 'Admin User', role: 'admin', is_active: true },
    }),
    changePassword: vi.fn(),
    updateProfile: vi.fn(),
  },
  brandingApi: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    update: vi.fn(),
    uploadLogo: vi.fn(),
  },
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

describe('SettingsPage', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders the page title', () => {
    renderWithProviders(<SettingsPage />)
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('renders Security tab', () => {
    renderWithProviders(<SettingsPage />)
    expect(screen.getByText('Security')).toBeInTheDocument()
  })
})
