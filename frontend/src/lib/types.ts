/** Shared TypeScript interfaces for the EDQ frontend. */

export type TestRunStatus =
  | 'pending'
  | 'selecting_interface'
  | 'syncing'
  | 'running'
  | 'paused_manual'
  | 'paused_cable'
  | 'awaiting_manual'
  | 'awaiting_review'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface ReadinessSummary {
  score: number
  level: string
  label: string
  report_ready: boolean
  operational_ready: boolean
  blocking_issue_count: number
  pending_manual_count: number
  release_blocking_failure_count: number
  review_required_issue_count: number
  manual_evidence_pending_count: number
  advisory_count: number
  override_count: number
  failed_test_count: number
  completed_result_count: number
  total_result_count: number
  trust_tier_counts: Record<string, number>
  reasons: string[]
  next_step: string
  summary: string
}

export interface Device {
  id: string
  ip_address: string | null
  mac_address: string | null
  addressing_mode: 'static' | 'dhcp' | 'unknown' | null
  hostname: string | null
  name: string | null
  manufacturer: string | null
  model: string | null
  firmware_version: string | null
  serial_number: string | null
  category: string
  status: string
  location: string | null
  oui_vendor: string | null
  os_fingerprint: string | null
  open_ports: PortEntry[] | null
  discovery_data: Record<string, unknown> | null
  notes: string | null
  profile_id: string | null
  discovered_by: string | null
  last_tested: string | null
  last_seen_at: string | null
  last_verdict: string | null
  project_id: string | null
  created_at: string
  updated_at: string
}

export interface PortEntry {
  port: number
  protocol: string
  service: string
  version?: string
}

export interface TestRun {
  id: string
  device_id: string
  device_name: string | null
  device_ip: string | null
  device_mac_address: string | null
  device_manufacturer: string | null
  device_model: string | null
  device_category: string | null
  template_id: string | null
  template_name: string | null
  engineer_id: string
  engineer_name: string | null
  agent_id: string | null
  status: TestRunStatus
  overall_verdict: string | null
  progress_pct: number | null
  total_tests: number | null
  completed_tests: number | null
  passed_tests: number | null
  failed_tests: number | null
  advisory_tests: number | null
  na_tests: number | null
  synopsis: string | null
  synopsis_status: string | null
  connection_scenario: string | null
  run_metadata: Record<string, unknown> | null
  created_at: string
  confidence: number | null
  readiness_summary: ReadinessSummary | null
  started_at: string | null
  updated_at: string | null
  completed_at: string | null
}

export interface TestResult {
  id: string
  test_run_id: string
  test_id: string
  test_name: string
  verdict: string | null
  comment: string | null
  comment_override: string | null
  engineer_notes: string | null
  findings: Record<string, unknown> | unknown[] | null
  raw_output: string | null
  parsed_data: Record<string, unknown> | unknown[] | null
  tool: string | null
  tier: string
  is_essential: string | null
  is_overridden: boolean
  override_reason: string | null
  override_verdict: string | null
  overridden_by_user_id: string | null
  overridden_by_username: string | null
  overridden_at: string | null
  duration_seconds: number | null
  evidence_files: string[] | null
  compliance_map: string[] | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string | null
}

export interface TestTemplate {
  id: string
  name: string
  description: string | null
  test_ids: string[]
  device_category: string | null
  is_default: boolean
  created_at: string
}

export interface TestLibraryItem {
  test_id: string
  name: string
  description: string
  tier: string
  tool: string | null
  is_essential: boolean
  category: string
  compliance_refs: string[]
}

export interface TestPlan {
  id: string
  name: string
  description: string | null
  base_template_id: string | null
  test_configs: TestConfig[]
  created_by: string
  created_at: string
  updated_at: string | null
}

export interface TestConfig {
  test_id: string
  enabled: boolean
  tier_override: string | null
  custom?: {
    name: string
    description: string
    tier: string
  } | null
}

export interface WhitelistEntry {
  port: number
  protocol: string
  service: string
  required_version?: string | null
}

export interface Whitelist {
  id: string
  name: string
  description: string | null
  is_default: boolean
  entries: WhitelistEntry[]
  created_at: string
}

export interface AuditLogEntry {
  id: string
  user_id: string | null
  user_name: string | null
  action: string
  resource_type: string
  resource_id: string | null
  details: Record<string, unknown> | null
  ip_address: string | null
  compliance_refs: string[] | null
  created_at: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  skip: number
  limit: number
}

export interface UserProfile {
  id: string
  username: string
  email: string
  full_name: string | null
  role: 'engineer' | 'reviewer' | 'admin'
  is_active: boolean
  last_login: string | null
  created_at: string
}

export interface ScanSchedule {
  id: string
  device_id: string
  template_id: string
  created_by: string
  frequency: 'daily' | 'weekly' | 'monthly'
  is_active: boolean
  last_run_at: string | null
  next_run_at: string
  run_count: number
  max_runs: number | null
  diff_summary: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface CVEResult {
  id: string
  description: string
  severity: string
  cvss_score: number | null
  url: string
}

export interface ServiceCVEResult {
  port: number
  service: string
  version: string
  cves: CVEResult[]
}

export interface CVELookupResponse {
  status: string
  query: string
  total_cves: number
  results: ServiceCVEResult[]
  keyword_results: CVEResult[]
}

export interface DiscoveredDevice {
  id: string
  ip_address: string
  mac_address?: string | null
  hostname: string | null
  oui_vendor?: string | null
  os_fingerprint?: string | null
  open_ports?: PortEntry[] | null
  manufacturer: string | null
  model: string | null
  predicted_name: string | null
  category: string
  status?: string
  is_new: boolean
  reachability_verified?: boolean
  project_id?: string | null
}

export type DeviceCreateResponse = Device & { reachability_verified?: boolean }

export interface DiscoveryScanResponse {
  status: string
  target: string
  devices_found: number
  devices: DiscoveredDevice[]
  unreachable_skipped?: number
  message?: string
}

export interface ReportTemplate {
  key: string
  name?: string
  label?: string
  category?: string
  device_category?: string
}

export interface Project {
  id: string
  name: string
  description: string | null
  status: 'active' | 'archived' | 'completed'
  created_by: string
  client_name: string | null
  location: string | null
  device_count: number
  test_run_count: number
  created_at: string
  updated_at: string
  is_archived: boolean
}

export interface TourState {
  showWelcomeBanner: boolean
  startTour: () => void
  dismissTour: () => void
  restartTour?: () => void
}
