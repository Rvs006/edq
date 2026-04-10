import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import App from '@/App'

const authState = {
  role: 'engineer' as 'engineer' | 'reviewer' | 'admin',
  isAuthenticated: true,
  loading: false,
}

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: authState.isAuthenticated
      ? {
          id: '1',
          username: 'user1',
          email: 'user1@example.com',
          full_name: 'User One',
          role: authState.role,
          is_active: true,
        }
      : null,
    loading: authState.loading,
    isAuthenticated: authState.isAuthenticated,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}))

vi.mock('@/components/layout/DashboardLayout', () => ({
  default: ({ children }: { children: unknown }) => children,
}))

vi.mock('@/components/common/ErrorBoundary', () => ({
  ErrorBoundary: ({ children }: { children: unknown }) => children,
  PageErrorBoundary: ({ children }: { children: unknown }) => children,
}))

vi.mock('@/components/common/SkipToContent', () => ({
  default: () => null,
}))

vi.mock('@/components/tour/GuidedTour', () => ({
  default: () => null,
  useTourState: () => ({
    tourActive: false,
    currentStep: 0,
    setCurrentStep: vi.fn(),
    skipTour: vi.fn(),
    completeTour: vi.fn(),
    showWelcomeBanner: false,
    startTour: vi.fn(),
    dismissTour: vi.fn(),
  }),
}))

vi.mock('@/pages/LandingPage', () => ({ default: () => 'Landing Page' }))
vi.mock('@/pages/LoginPage', () => ({ default: () => 'Login Page' }))
vi.mock('@/pages/DashboardPage', () => ({ default: () => 'Dashboard Page' }))
vi.mock('@/pages/DevicesPage', () => ({ default: () => 'Devices Page' }))
vi.mock('@/pages/DeviceDetailPage', () => ({ default: () => 'Device Detail Page' }))
vi.mock('@/pages/DeviceComparePage', () => ({ default: () => 'Device Compare Page' }))
vi.mock('@/pages/TestRunsPage', () => ({ default: () => 'Test Runs Page' }))
vi.mock('@/pages/TestRunDetailPage', () => ({ default: () => 'Test Run Detail Page' }))
vi.mock('@/pages/TemplatesPage', () => ({ default: () => 'Templates Page' }))
vi.mock('@/pages/WhitelistsPage', () => ({ default: () => 'Whitelists Page' }))
vi.mock('@/pages/ReportsPage', () => ({ default: () => 'Reports Page' }))
vi.mock('@/pages/AuditLogPage', () => ({ default: () => 'Audit Log Page' }))
vi.mock('@/pages/SettingsPage', () => ({ default: () => 'Settings Page' }))
vi.mock('@/pages/ReviewQueuePage', () => ({ default: () => 'Review Queue Page' }))
vi.mock('@/pages/AdminPage', () => ({ default: () => 'Admin Page' }))
vi.mock('@/pages/NetworkScanPage', () => ({ default: () => 'Network Scan Page' }))
vi.mock('@/pages/TestPlansPage', () => ({ default: () => 'Test Plans Page' }))
vi.mock('@/pages/ScanSchedulesPage', () => ({ default: () => 'Scan Schedules Page' }))
vi.mock('@/pages/AgentsPage', () => ({ default: () => 'Agents Page' }))
vi.mock('@/pages/DeviceProfilesPage', () => ({ default: () => 'Device Profiles Page' }))
vi.mock('@/pages/AuthorizedNetworksPage', () => ({ default: () => 'Authorized Networks Page' }))
vi.mock('@/pages/ProjectsPage', () => ({ default: () => 'Projects Page' }))
vi.mock('@/pages/NotFoundPage', () => ({ default: () => 'Not Found Page' }))

function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

describe('App route permissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.role = 'engineer'
    authState.isAuthenticated = true
    authState.loading = false
  })

  it('lets engineers open backend-readable routes that were previously frontend-blocked', () => {
    renderApp('/templates')
    expect(screen.getByText('Templates Page')).toBeInTheDocument()
  })

  it('lets engineers open authorized networks for read access', () => {
    renderApp('/authorized-networks')
    expect(screen.getByText('Authorized Networks Page')).toBeInTheDocument()
  })

  it('lets reviewers open the audit log', () => {
    authState.role = 'reviewer'
    renderApp('/audit-log')
    expect(screen.getByText('Audit Log Page')).toBeInTheDocument()
  })

  it('lets engineers open scan schedules for read-only access', () => {
    renderApp('/scan-schedules')
    expect(screen.getByText('Scan Schedules Page')).toBeInTheDocument()
  })

  it('still blocks engineers from admin-only routes', () => {
    renderApp('/admin')
    expect(screen.getByText('Access denied')).toBeInTheDocument()
  })
})
