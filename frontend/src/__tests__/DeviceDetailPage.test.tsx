import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AxiosHeaders, type AxiosResponse } from 'edq-http'

import DeviceDetailPage from '@/pages/DeviceDetailPage'
import { discoveryApi } from '@/lib/api'
import type { DiscoveryScanResponse } from '@/lib/types'
import toast from 'react-hot-toast'

const mockRole = {
  value: 'engineer' as 'engineer' | 'reviewer' | 'admin',
}

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
    get: vi.fn().mockResolvedValue({
      data: {
        id: '1',
        ip_address: '192.168.1.100',
        mac_address: 'AA:BB:CC:DD:EE:FF',
        addressing_mode: 'static',
        hostname: 'cam-lobby',
        name: null,
        manufacturer: 'Axis',
        model: 'P3245',
        firmware_version: '10.12',
        serial_number: null,
        category: 'camera',
        status: 'tested',
        location: null,
        oui_vendor: null,
        os_fingerprint: null,
        open_ports: [],
        discovery_data: null,
        notes: null,
        profile_id: null,
        discovered_by: null,
        last_tested: null,
        last_verdict: 'pass',
        project_id: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    }),
    update: vi.fn(),
    delete: vi.fn(),
    trends: vi.fn().mockResolvedValue({ data: { runs: [], trend: 'stable' } }),
    discoverIp: vi.fn(),
  },
  testRunsApi: {
    list: vi.fn().mockResolvedValue({ data: [] }),
  },
  cveApi: {
    lookup: vi.fn(),
  },
  discoveryApi: {
    scan: vi.fn(),
  },
  getApiErrorMessage: vi.fn((_err: unknown, fallback: string) => fallback),
}))

vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

function renderWithProviders() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/devices/1']}>
        <Routes>
          <Route path="/devices/:id" element={<DeviceDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DeviceDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRole.value = 'engineer'
  })

  it('hides the delete button for engineers', async () => {
    renderWithProviders()

    expect(await screen.findByText('cam-lobby')).toBeInTheDocument()
    expect(screen.queryByLabelText('Delete device')).not.toBeInTheDocument()
  })

  it('shows the delete button for admins', async () => {
    mockRole.value = 'admin'
    renderWithProviders()

    expect(await screen.findByText('cam-lobby')).toBeInTheDocument()
    expect(screen.getByLabelText('Delete device')).toBeInTheDocument()
  })

  it('shows an unreachable warning when auto-detect finds no device', async () => {
    const scanResponse: AxiosResponse<DiscoveryScanResponse> = {
      data: {
        status: 'complete',
        target: '192.168.1.100',
        devices_found: 0,
        devices: [],
        message: 'Device 192.168.1.100 is not reachable. Check that the cable is connected and the device is powered on.',
      },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: { headers: new AxiosHeaders() },
    }
    vi.mocked(discoveryApi.scan).mockResolvedValue(scanResponse)

    const user = userEvent.setup()
    renderWithProviders()

    expect(await screen.findByText('cam-lobby')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /auto-detect/i }))

    expect(await screen.findByText(/Device 192\.168\.1\.100 is not reachable/)).toBeInTheDocument()
    expect(screen.queryByText('Device re-scanned successfully. Information updated.')).not.toBeInTheDocument()
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('192.168.1.100 is not reachable'))
  })
})
