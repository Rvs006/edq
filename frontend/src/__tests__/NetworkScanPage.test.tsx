import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import NetworkScanPage from '@/pages/NetworkScanPage'

vi.mock('@/lib/api', () => ({
  discoveryApi: {
    scan: vi.fn(),
    registerDevice: vi.fn(),
  },
  devicesApi: {
    list: vi.fn().mockResolvedValue({ data: [] }),
    create: vi.fn(),
  },
  networkScanApi: {
    detectNetworks: vi.fn().mockResolvedValue({ data: { networks: [] } }),
    discoverDevices: vi.fn(),
  },
  authorizedNetworksApi: {
    list: vi.fn().mockResolvedValue({ data: [] }),
  },
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
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('NetworkScanPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the page title', () => {
    renderWithProviders(<NetworkScanPage />)
    expect(screen.getByText('Network Discovery')).toBeInTheDocument()
  })

  it('renders CIDR input', () => {
    renderWithProviders(<NetworkScanPage />)
    expect(screen.getByText('CIDR Range')).toBeInTheDocument()
  })

  it('renders scan button', () => {
    renderWithProviders(<NetworkScanPage />)
    expect(screen.getByText('Scan Network')).toBeInTheDocument()
  })
})
