import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ReportsPage from '@/pages/ReportsPage'

vi.mock('@/lib/api', () => ({
  reportsApi: {
    list: vi.fn().mockResolvedValue({ data: [] }),
    templates: vi.fn().mockResolvedValue({ data: [] }),
    generate: vi.fn(),
    download: vi.fn(),
  },
  testRunsApi: {
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

describe('ReportsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the page title', () => {
    renderWithProviders(<ReportsPage />)
    expect(screen.getByText('Reports')).toBeInTheDocument()
  })

  it('renders generate report section', () => {
    renderWithProviders(<ReportsPage />)
    expect(screen.getAllByText('Generate Report').length).toBeGreaterThan(0)
  })

  it('renders without crashing', () => {
    renderWithProviders(<ReportsPage />)
    expect(document.body).toBeTruthy()
  })

  it('groups exports into spreadsheet and document sections', () => {
    renderWithProviders(<ReportsPage />)
    expect(screen.getByText('Spreadsheet Exports')).toBeInTheDocument()
    expect(screen.getByText('Document Exports')).toBeInTheDocument()
  })

  it('shows template profile guidance for all formats', () => {
    renderWithProviders(<ReportsPage />)
    expect(screen.getByText(/template profile now applies to Excel, CSV, Word, and PDF outputs/i)).toBeInTheDocument()
  })

  it('shows readiness content in the report contents list', () => {
    renderWithProviders(<ReportsPage />)
    expect(screen.getByText(/Operational readiness score and trust summary/i)).toBeInTheDocument()
  })
})
