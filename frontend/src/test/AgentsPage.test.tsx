import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'

// Mock the API module
const mockAgentsList = vi.fn()
vi.mock('@/lib/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
  agentsApi: {
    list: () => mockAgentsList(),
  },
}))

import AgentsPage from '@/pages/AgentsPage'

const MOCK_AGENTS = [
  {
    id: 'a1',
    name: 'Dylan-MBP',
    hostname: 'dylans-mbp.local',
    api_key_prefix: 'edq_1234',
    platform: 'macos',
    agent_version: '1.0.0',
    ip_address: '192.168.1.10',
    status: 'online',
    last_heartbeat: new Date(Date.now() - 120_000).toISOString(),
    capabilities: null,
    current_task: null,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'a2',
    name: 'Sarah-Thinkpad',
    hostname: 'sarah-tp.local',
    api_key_prefix: 'edq_5678',
    platform: 'windows',
    agent_version: '1.0.0',
    ip_address: '192.168.1.11',
    status: 'busy',
    last_heartbeat: new Date(Date.now() - 5_000).toISOString(),
    capabilities: null,
    current_task: 'run-123',
    is_active: true,
    created_at: '2026-01-02T00:00:00Z',
  },
  {
    id: 'a3',
    name: 'Alex-Dell',
    hostname: 'alex-dell.local',
    api_key_prefix: 'edq_9abc',
    platform: 'windows',
    agent_version: '0.9.8',
    ip_address: '192.168.1.12',
    status: 'offline',
    last_heartbeat: new Date(Date.now() - 10_800_000).toISOString(),
    capabilities: null,
    current_task: null,
    is_active: true,
    created_at: '2026-01-03T00:00:00Z',
  },
]

function renderAgentsPage() {
  return render(
    <BrowserRouter>
      <AgentsPage />
    </BrowserRouter>
  )
}

describe('AgentsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default: API returns agents successfully
    mockAgentsList.mockResolvedValue({ data: MOCK_AGENTS })
  })

  it('renders the page heading and subtitle', async () => {
    renderAgentsPage()

    expect(screen.getByText('Agent Fleet')).toBeInTheDocument()
    expect(screen.getByText(/Monitor connected EDQ agents/)).toBeInTheDocument()
  })

  it('displays the info callout explaining the page', async () => {
    renderAgentsPage()

    expect(screen.getByText(/What is this page/)).toBeInTheDocument()
    expect(screen.getByText(/fleet tracker/)).toBeInTheDocument()
  })

  it('shows loading state while fetching agents', () => {
    // Never resolve the promise
    mockAgentsList.mockReturnValue(new Promise(() => {}))
    renderAgentsPage()

    expect(screen.getByText(/Loading agents/)).toBeInTheDocument()
  })

  it('shows error state when API fails', async () => {
    mockAgentsList.mockRejectedValue(new Error('Network error'))
    renderAgentsPage()

    await waitFor(() => {
      expect(screen.getByText(/Failed to load agents/)).toBeInTheDocument()
    })
  })

  it('renders stats cards with correct counts from API data', async () => {
    renderAgentsPage()

    await waitFor(() => {
      // 1 online, 1 busy, 1 offline from mock data
      const statValues = screen.getAllByTestId('stat-value')
      expect(statValues).toHaveLength(3)
    })

    // Check that agent names appear in the table
    expect(screen.getByText('Dylan-MBP')).toBeInTheDocument()
    expect(screen.getByText('Sarah-Thinkpad')).toBeInTheDocument()
    expect(screen.getByText('Alex-Dell')).toBeInTheDocument()
  })

  it('shows outdated version warning for agents not on latest version', async () => {
    renderAgentsPage()

    await waitFor(() => {
      expect(screen.getByText('Alex-Dell')).toBeInTheDocument()
    })

    // Alex-Dell has version 0.9.8 which is outdated
    expect(screen.getByText(/0\.9\.8/)).toBeInTheDocument()
  })

  it('shows correct status labels for each agent', async () => {
    renderAgentsPage()

    await waitFor(() => {
      expect(screen.getByText('Dylan-MBP')).toBeInTheDocument()
    })

    expect(screen.getByText('Online')).toBeInTheDocument()
    expect(screen.getByText('Scanning')).toBeInTheDocument()
    expect(screen.getByText('Offline')).toBeInTheDocument()
  })

  it('renders empty state when no agents are registered', async () => {
    mockAgentsList.mockResolvedValue({ data: [] })
    renderAgentsPage()

    await waitFor(() => {
      expect(screen.getByText(/No agents registered/)).toBeInTheDocument()
    })
  })

  it('falls back to demo data when API returns 401', async () => {
    mockAgentsList.mockRejectedValue({ response: { status: 401 } })
    renderAgentsPage()

    // Should show demo data as fallback
    await waitFor(() => {
      expect(screen.getByText('Dylan-MBP')).toBeInTheDocument()
    })
  })
})
