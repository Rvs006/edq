import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ReportsPage from '@/pages/ReportsPage'
import { reportsApi, testRunsApi } from '@/lib/api'
import type { TestRun } from '@/lib/types'
import toast from 'react-hot-toast'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'edq-http'

vi.mock('@/lib/api', () => ({
  reportsApi: {
    templates: vi.fn().mockResolvedValue({ data: [] }),
    generate: vi.fn(),
    download: vi.fn(),
  },
  resolveApiUrl: vi.fn((path: string) => path),
  getApiErrorMessage: vi.fn((_err: unknown, fallback: string) => fallback),
  testRunsApi: {
    list: vi.fn().mockResolvedValue({ data: [] }),
  },
}))

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

function axiosResponse<T>(data: T, overrides: Partial<AxiosResponse<T>> = {}): AxiosResponse<T> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config: {} as InternalAxiosRequestConfig,
    ...overrides,
  }
}

function makeTestRun(overrides: Partial<TestRun> = {}): TestRun {
  return {
    id: 'run-1',
    device_id: 'device-1',
    device_name: null,
    device_ip: '192.0.2.10',
    device_mac_address: null,
    device_manufacturer: 'FixtureCo',
    device_model: 'FX-100',
    device_category: 'controller',
    template_id: null,
    template_name: 'Full Security Assessment',
    engineer_id: 'engineer-1',
    engineer_name: 'Admin User',
    agent_id: null,
    status: 'completed',
    overall_verdict: null,
    progress_pct: 100,
    total_tests: 0,
    completed_tests: 0,
    passed_tests: 0,
    failed_tests: 0,
    advisory_tests: 0,
    na_tests: 0,
    synopsis: null,
    synopsis_status: null,
    connection_scenario: null,
    run_metadata: null,
    created_at: '2026-05-11T10:00:00Z',
    confidence: null,
    readiness_summary: {
      score: 10,
      level: 'ready',
      label: 'Ready',
      report_ready: true,
      operational_ready: true,
      blocking_issue_count: 0,
      pending_manual_count: 0,
      release_blocking_failure_count: 0,
      review_required_issue_count: 0,
      manual_evidence_pending_count: 0,
      advisory_count: 0,
      override_count: 0,
      failed_test_count: 0,
      completed_result_count: 0,
      total_result_count: 0,
      trust_tier_counts: {},
      reasons: [],
      next_step: 'Ready for report generation.',
      summary: 'Ready for report generation.',
    },
    started_at: null,
    updated_at: null,
    completed_at: null,
    ...overrides,
  }
}

function renderWithProviders(ui: React.ReactElement, options: { completedRuns?: TestRun[] } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  })
  if (options.completedRuns) {
    queryClient.setQueryData(['completed-runs'], options.completedRuns)
  }
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('ReportsPage', () => {
  const completedRun = makeTestRun()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(testRunsApi.list).mockResolvedValue(axiosResponse([]))
    vi.mocked(reportsApi.templates).mockResolvedValue(axiosResponse([]))
    Object.defineProperty(window.URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:report-download'),
    })
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
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

  it('groups exports into Excel and Word sections', () => {
    renderWithProviders(<ReportsPage />)
    expect(screen.getByText('Spreadsheet Exports')).toBeInTheDocument()
    expect(screen.getByText('Document Exports')).toBeInTheDocument()
    expect(screen.getByText('Excel')).toBeInTheDocument()
    expect(screen.getByText('Word')).toBeInTheDocument()
    expect(screen.queryByText('PDF')).not.toBeInTheDocument()
    expect(screen.queryByText('CSV')).not.toBeInTheDocument()
    expect(screen.queryByText('CAD')).not.toBeInTheDocument()
  })

  it('shows template profile guidance for Excel and Word only', () => {
    renderWithProviders(<ReportsPage />)
    expect(screen.getByText(/canonical report profile applies to Excel and Word outputs/i)).toBeInTheDocument()
  })

  it('shows readiness content in the report contents list', () => {
    renderWithProviders(<ReportsPage />)
    expect(screen.getByText(/Operational readiness score and trust summary/i)).toBeInTheDocument()
  })

  it('explains that synopsis drafting is server-side when no run is selected', () => {
    renderWithProviders(<ReportsPage />)
    expect(screen.getByText(/server-side provider settings/i)).toBeInTheDocument()
  })

  it('shows the excel workbook preview by default', () => {
    renderWithProviders(<ReportsPage />)
    expect(screen.getByText('Excel Workbook Preview')).toBeInTheDocument()
    expect(screen.getByText(/workbook tabs: General Test Information, Test Results, Additional Device Information, Raw Evidence/i)).toBeInTheDocument()
  })

  it('groups report-ready runs by device and marks the latest timestamp', async () => {
    const olderRun = makeTestRun({
      id: 'run-old',
      created_at: '2026-05-10T10:00:00Z',
      completed_at: '2026-05-10T10:30:00Z',
      template_name: 'Universal (Smart Profiling)',
    })
    const newerRun = makeTestRun({
      id: 'run-new',
      created_at: '2026-05-12T10:00:00Z',
      completed_at: '2026-05-12T10:30:00Z',
      template_name: 'Extended Qualification (Dylan Template)',
    })

    renderWithProviders(<ReportsPage />, { completedRuns: [olderRun, newerRun] })

    const select = await screen.findByLabelText('Select test run')
    expect(select.querySelector('optgroup[label="FixtureCo FX-100 (2)"]')).not.toBeNull()
    expect(screen.getByRole('option', { name: /Latest - FixtureCo FX-100/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Extended Qualification/i })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Full Security Assessment/i })).toBeInTheDocument()
  })

  it('downloads the generated report as a blob via axios', async () => {
    const filename = 'EDQ_Report_12345678-1234-1234-1234-123456789abc_generic_20260511_100000.xlsx'
    vi.mocked(reportsApi.generate).mockResolvedValueOnce(
      axiosResponse({
        filename,
        download_url: `/api/reports/download/${filename}`,
      }),
    )
    vi.mocked(reportsApi.download).mockResolvedValueOnce(axiosResponse(
      new Blob([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      }),
      { headers: { 'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' } },
    ))

    renderWithProviders(<ReportsPage />, { completedRuns: [completedRun] })

    await screen.findByRole('option', { name: /FixtureCo FX-100/i })
    fireEvent.change(screen.getByLabelText('Select test run'), { target: { value: 'run-1' } })
    fireEvent.click(screen.getByRole('button', { name: /generate report/i }))

    await waitFor(() => expect(reportsApi.generate).toHaveBeenCalledWith({
      test_run_id: 'run-1',
      report_type: 'excel',
      include_synopsis: true,
      template_key: 'generic',
    }))
    await waitFor(() => expect(reportsApi.download).toHaveBeenCalledWith(filename))
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalledWith(`Report generated: ${filename}`)
  })

  it('surfaces a clear error when the download response is JSON instead of a workbook', async () => {
    const filename = 'EDQ_Report_12345678-1234-1234-1234-123456789abc_generic_20260511_100000.xlsx'
    vi.mocked(reportsApi.generate).mockResolvedValueOnce(
      axiosResponse({ filename, download_url: `/api/reports/download/${filename}` }),
    )
    vi.mocked(reportsApi.download).mockResolvedValueOnce(
      axiosResponse(
        new Blob([JSON.stringify({ detail: 'Access denied' })], { type: 'application/json' }),
        { headers: { 'content-type': 'application/json' } },
      ),
    )

    renderWithProviders(<ReportsPage />, { completedRuns: [completedRun] })
    await screen.findByRole('option', { name: /FixtureCo FX-100/i })
    fireEvent.change(screen.getByLabelText('Select test run'), { target: { value: 'run-1' } })
    fireEvent.click(screen.getByRole('button', { name: /generate report/i }))

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
  })
})
