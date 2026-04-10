import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import DevicesPage from '@/pages/DevicesPage'

const { mockDiscoveryScan, mockRole } = vi.hoisted(() => ({
  mockDiscoveryScan: vi.fn(),
  mockRole: {
    value: 'engineer' as 'engineer' | 'reviewer' | 'admin',
  },
}))

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: '1',
      username: 'user1',
      email: 'user1@example.com',
      full_name: 'User One',
      role: mockRole.value,
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
  devicesApi: {
    list: vi.fn().mockResolvedValue({
      data: [
        {
          id: '1',
          ip_address: '192.168.1.100',
          hostname: 'cam-lobby',
          manufacturer: 'Axis',
          model: 'P3245',
          firmware_version: '10.12',
          category: 'camera',
          status: 'tested',
          last_tested: '2026-01-01T00:00:00Z',
          last_verdict: 'pass',
          mac_address: 'AA:BB:CC:DD:EE:FF',
          name: null,
          serial_number: null,
          location: null,
          oui_vendor: null,
          os_fingerprint: null,
          open_ports: null,
          discovery_data: null,
          notes: null,
          profile_id: null,
          discovered_by: null,
          project_id: null,
          addressing_mode: 'static',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
    }),
    create: vi.fn(),
    delete: vi.fn(),
  },
  discoveryApi: {
    scan: mockDiscoveryScan,
    registerDevice: vi.fn(),
  },
  healthApi: {
    systemStatus: vi.fn().mockResolvedValue({
      data: {
        tools_sidecar: { status: 'ok' },
      },
    }),
  },
  projectsApi: {
    list: vi.fn().mockResolvedValue({ data: [] }),
  },
  getApiErrorMessage: vi.fn((_err: unknown, fallback: string) => fallback),
}))

vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

function renderWithProviders(initialEntries: string[] = ['/devices']) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <DevicesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DevicesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole.value = 'engineer'
    mockDiscoveryScan.mockReset()
  })

  it('renders the device list and core actions', async () => {
    renderWithProviders()

    expect(screen.getByText('Devices')).toBeInTheDocument()
    expect(screen.getByText('Add Device')).toBeInTheDocument()
    expect(screen.getByText('Discover')).toBeInTheDocument()
    expect(await screen.findByText('Axis P3245')).toBeInTheDocument()
  })

  it('hides bulk delete controls for engineers', async () => {
    const user = userEvent.setup()
    renderWithProviders()

    await screen.findByText('Axis P3245')
    await user.click(screen.getByLabelText('Select Axis P3245'))

    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('shows bulk delete controls for admins', async () => {
    mockRole.value = 'admin'
    const user = userEvent.setup()
    renderWithProviders()

    await screen.findByText('Axis P3245')
    await user.click(screen.getByLabelText('Select Axis P3245'))

    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
  })

  it('passes the active project filter through discovery requests', async () => {
    mockDiscoveryScan.mockResolvedValue({
      data: {
        status: 'complete',
        target: '192.168.1.10',
        devices_found: 1,
        devices: [
          {
            id: 'device-2',
            ip_address: '192.168.1.10',
            hostname: 'easyio-1',
            manufacturer: 'EasyIO',
            model: 'FS-32',
            predicted_name: 'EasyIO FS-32',
            category: 'controller',
            is_new: true,
            project_id: 'proj-1',
          },
        ],
      },
    })

    const user = userEvent.setup()
    renderWithProviders(['/devices?project_id=proj-1'])

    await user.click(screen.getByRole('button', { name: 'Discover' }))
    await user.type(screen.getByPlaceholderText('192.168.1.10'), '192.168.1.10')
    await user.click(screen.getByRole('button', { name: 'Start Discovery' }))

    expect(mockDiscoveryScan).toHaveBeenCalledWith({
      ip_address: '192.168.1.10',
      project_id: 'proj-1',
    })
    expect(await screen.findByText('Click a result to open it')).toBeInTheDocument()
  })
})
