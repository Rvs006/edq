export type NetworkScanStep = 'configure' | 'review' | 'monitor' | 'results'

export interface DiscoveredDevice {
  ip: string
  mac: string | null
  vendor: string | null
  hostname: string | null
  services?: string[]
  open_ports?: number[]
  os?: string | null
  model?: string | null
  http_server?: string | null
}

export type DeviceViewMode = 'grid' | 'tree'

export interface TestDetail {
  test_id: string
  test_name: string
  verdict: string
  tool: string | null
  duration_seconds: number | null
  is_essential: string
  tier: string
  comment: string | null
  raw_output: string | null
  started_at: string | null
  completed_at: string | null
}

export interface ScanResult {
  run_id: string
  device_ip: string
  device_id: string
  device_name?: string | null
  device_category: string | null
  vendor: string | null
  hostname: string | null
  model?: string | null
  status: string
  progress_pct: number
  total_tests: number
  completed_tests: number
  passed_tests: number
  failed_tests: number
  advisory_tests: number
  overall_verdict: string | null
  test_details: TestDetail[]
}

export const SCENARIO_PRESELECTS: Record<string, string[]> = {
  test_lab: ['U01', 'U02', 'U06', 'U07', 'U08', 'U09', 'U10', 'U11', 'U12', 'U15', 'U16', 'U19', 'U34'],
  direct: ['U01', 'U06', 'U08', 'U10', 'U16'],
  site_network: ['U01', 'U02', 'U06', 'U08'],
}

export const SCENARIOS = [
  { value: 'test_lab', label: 'Test Lab', desc: 'Isolated test environment — full scan safe' },
  { value: 'direct', label: 'Direct Connection', desc: 'Point-to-point with device — most scans safe' },
  { value: 'site_network', label: 'Site Network', desc: 'Production network — limited scans recommended', warn: true },
]

export const ACTIVE_NETWORK_SCAN_STATUSES = new Set(['pending', 'discovering', 'scanning'])
export const ACTIVE_TEST_RUN_STATUSES = new Set(['pending', 'selecting_interface', 'syncing', 'running', 'paused_manual', 'paused_cable'])
export const COMPLETED_TEST_RUN_STATUSES = new Set(['completed', 'awaiting_manual', 'awaiting_review'])
export const ERROR_TEST_RUN_STATUSES = new Set(['failed', 'error', 'cancelled'])

export function normalizeNetworkScanStatus(status: string | null | undefined): string {
  return String(status || '').toLowerCase()
}

export function loadPersistedScanState(): { scanId: string | null; step: NetworkScanStep } {
  try {
    const raw = sessionStorage.getItem('edq_active_scan')
    if (raw) {
      const savedState = JSON.parse(raw)
      if (savedState.scanId && (savedState.step === 'review' || savedState.step === 'monitor' || savedState.step === 'results')) {
        return { scanId: savedState.scanId, step: savedState.step }
      }
    }
  } catch {
    // Ignore storage corruption and fall back to the default state.
  }
  return { scanId: null, step: 'configure' }
}

export function savePersistedScanState(scanId: string | null, step: NetworkScanStep) {
  if (scanId && (step === 'review' || step === 'monitor' || step === 'results')) {
    sessionStorage.setItem('edq_active_scan', JSON.stringify({ scanId, step }))
    return
  }
  sessionStorage.removeItem('edq_active_scan')
}
