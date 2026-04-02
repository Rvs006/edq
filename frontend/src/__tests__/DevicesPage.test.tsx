import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import DevicesPage from '@/pages/DevicesPage'

// Mock the API module
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
          last_tested: '2026-01-01',
          last_verdict: 'pass',
          mac_address: null,
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
          created_at: '2026-01-01',
          updated_at: '2026-01-01',
        },
      ],
    }),
    create: vi.fn(),
    stats: vi.fn().mockResolvedValue({ data: { total: 1, by_status: {}, by_category: {} } }),
  },
  discoveryApi: {
    scan: vi.fn(),
    registerDevice: vi.fn(),
  },
}))

// Mock react-hot-toast
vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('DevicesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the page title', () => {
    renderWithProviders(<DevicesPage />)
    expect(screen.getByText('Devices')).toBeInTheDocument()
  })

  it('renders the subtitle', () => {
    renderWithProviders(<DevicesPage />)
    expect(screen.getByText('Manage known devices first, then use discovery when the address is unknown')).toBeInTheDocument()
  })

  it('renders search input', () => {
    renderWithProviders(<DevicesPage />)
    expect(screen.getByPlaceholderText('Search by IP, hostname, manufacturer...')).toBeInTheDocument()
  })

  it('renders Add Device button', () => {
    renderWithProviders(<DevicesPage />)
    expect(screen.getByText('Add Device')).toBeInTheDocument()
  })

  it('renders Discover button', () => {
    renderWithProviders(<DevicesPage />)
    expect(screen.getByText('Discover')).toBeInTheDocument()
  })

  it('renders topology view toggle buttons', () => {
    renderWithProviders(<DevicesPage />)
    expect(screen.getByTitle('Table view')).toBeInTheDocument()
    expect(screen.getByTitle('Topology view')).toBeInTheDocument()
  })

  it('renders category filter dropdown', () => {
    renderWithProviders(<DevicesPage />)
    expect(screen.getByText('All Categories')).toBeInTheDocument()
  })
})
