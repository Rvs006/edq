import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

import NetworkScanPage from '@/pages/NetworkScanPage'

const { mockNetworkScanApi, mockAuthorizedNetworksApi, mockToast } = vi.hoisted(() => ({
  mockNetworkScanApi: {
    detectNetworks: vi.fn(),
    discover: vi.fn(),
    get: vi.fn(),
    start: vi.fn(),
    results: vi.fn(),
  },
  mockAuthorizedNetworksApi: {
    list: vi.fn(),
  },
  mockToast: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
  }),
}))

vi.mock('@/lib/api', () => ({
  networkScanApi: mockNetworkScanApi,
  templatesApi: {
    list: vi.fn(),
  },
  authorizedNetworksApi: mockAuthorizedNetworksApi,
}))

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: '1',
      username: 'user1',
      email: 'user1@example.com',
      full_name: 'User One',
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

vi.mock('@/hooks/useTestRunWebSocket', () => ({
  useTestRunWebSocket: vi.fn().mockReturnValue({
    terminalOutput: {},
    lastProgress: null,
  }),
}))

vi.mock('react-hot-toast', () => ({
  default: mockToast,
}))

function renderWithProviders() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <NetworkScanPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('NetworkScanPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.values(mockNetworkScanApi).forEach((mockFn) => mockFn.mockReset())
    mockAuthorizedNetworksApi.list.mockReset()
    sessionStorage.clear()
    mockAuthorizedNetworksApi.list.mockResolvedValue({
      data: [{ cidr: '192.168.1.0/24', label: 'Lab' }],
    })
    mockNetworkScanApi.detectNetworks.mockResolvedValue({ data: { interfaces: [] } })
    mockNetworkScanApi.get.mockResolvedValue({
      data: {
        id: 'scan-restored',
        status: 'pending',
        devices_found: [],
        selected_test_ids: [],
      },
    })
  })

  it('treats backend scanning status as active while the batch is running', async () => {
    const user = userEvent.setup()

    mockNetworkScanApi.discover.mockResolvedValue({
      data: {
        id: 'scan-1',
        status: 'pending',
        devices_found: [{ ip: '192.168.1.10', mac: null, vendor: 'Axis', hostname: 'cam-1' }],
      },
    })
    mockNetworkScanApi.start.mockResolvedValue({
      data: { status: 'scanning' },
    })
    mockNetworkScanApi.results.mockImplementation(() => new Promise(() => undefined))

    renderWithProviders()

    await user.click(screen.getByRole('button', { name: 'Discover Devices' }))
    expect(await screen.findByText('1 Device(s) Found')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Start Scan' }))

    expect(await screen.findByText('Scanning 0 device(s)...')).toBeInTheDocument()
    expect(screen.queryByText(/Scan complete/i)).not.toBeInTheDocument()
  }, 20000)

  it('surfaces awaiting_manual results with the backend status label', async () => {
    const user = userEvent.setup()

    mockNetworkScanApi.discover.mockResolvedValue({
      data: {
        id: 'scan-2',
        status: 'pending',
        devices_found: [{ ip: '192.168.1.11', mac: null, vendor: 'Axis', hostname: 'cam-2' }],
      },
    })
    mockNetworkScanApi.start.mockResolvedValue({
      data: { status: 'scanning' },
    })
    mockNetworkScanApi.results.mockResolvedValue({
      data: {
        status: 'complete',
        results: [
          {
            run_id: 'run-1',
            device_ip: '192.168.1.11',
            device_id: 'device-1',
            device_name: 'cam-2',
            device_category: 'camera',
            vendor: 'Axis',
            hostname: 'cam-2',
            model: 'P3245',
            status: 'awaiting_manual',
            progress_pct: 100,
            total_tests: 2,
            completed_tests: 2,
            passed_tests: 1,
            failed_tests: 0,
            advisory_tests: 0,
            overall_verdict: null,
            test_details: [],
          },
        ],
      },
    })

    renderWithProviders()

    await user.click(screen.getByRole('button', { name: 'Discover Devices' }))
    expect(await screen.findByText('1 Device(s) Found')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Start Scan' }))

    expect(await screen.findByText('Awaiting Manual')).toBeInTheDocument()
  }, 20000)

  it('allows a single-host /32 discovery range', async () => {
    const user = userEvent.setup()

    mockNetworkScanApi.discover.mockResolvedValue({
      data: {
        id: 'scan-3',
        status: 'pending',
        devices_found: [{ ip: '192.168.4.64', mac: null, vendor: 'EasyIO', hostname: null }],
      },
    })

    renderWithProviders()

    const cidrInput = screen.getByPlaceholderText('192.168.1.0/24')
    fireEvent.change(cidrInput, { target: { value: '192.168.4.64/32' } })

    expect(cidrInput).toHaveValue('192.168.4.64/32')
    expect(screen.getByText(/1 possible IPs/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Discover Devices' }))

    expect(mockNetworkScanApi.discover).toHaveBeenCalledWith(expect.objectContaining({
      cidr: '192.168.4.64/32',
    }))
    expect(await screen.findByText('192.168.4.64')).toBeInTheDocument()
  }, 20000)

  it('blocks invalid or over-wide CIDR ranges before discovery', async () => {
    renderWithProviders()

    const cidrInput = screen.getByPlaceholderText('192.168.1.0/24')
    const discoverButton = screen.getByRole('button', { name: 'Discover Devices' })

    fireEvent.change(cidrInput, { target: { value: '999.168.1.0/24' } })
    expect(screen.getByText('Invalid CIDR format')).toBeInTheDocument()
    expect(discoverButton).toBeDisabled()

    fireEvent.change(cidrInput, { target: { value: '10.0.0.0/8' } })
    expect(screen.getByText('CIDR prefix must be between /16 and /32')).toBeInTheDocument()
    expect(discoverButton).toBeDisabled()

    expect(mockNetworkScanApi.discover).not.toHaveBeenCalled()
  })

  it('shows backend start errors without entering an endless monitor state', async () => {
    const user = userEvent.setup()

    mockNetworkScanApi.discover.mockResolvedValue({
      data: {
        id: 'scan-4',
        status: 'pending',
        devices_found: [{ ip: '192.168.1.12', mac: null, vendor: 'Axis', hostname: 'cam-3' }],
      },
    })
    mockNetworkScanApi.start.mockResolvedValue({
      data: {
        status: 'error',
        error_message: 'No selected devices were reachable; no tests were started.',
        results: [],
      },
    })

    renderWithProviders()

    await user.click(screen.getByRole('button', { name: 'Discover Devices' }))
    expect(await screen.findByText('1 Device(s) Found')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Start Scan' }))

    expect(mockToast.error).toHaveBeenCalledWith('No selected devices were reachable; no tests were started.')
    expect(screen.queryByText(/Scanning 0 device\(s\)/i)).not.toBeInTheDocument()
    expect(mockNetworkScanApi.results).not.toHaveBeenCalled()
  }, 20000)
})
