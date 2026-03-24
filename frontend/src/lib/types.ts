/** Shared TypeScript interfaces for the EDQ frontend. */

export interface Device {
  id: string
  ip_address: string
  mac_address: string | null
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
  last_verdict: string | null
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
  template_id: string | null
  template_name: string | null
  status: string
  overall_verdict: string | null
  progress_pct: number | null
  total_tests: number | null
  completed_tests: number | null
  passed_tests: number | null
  failed_tests: number | null
  advisory_tests: number | null
  na_tests: number | null
  synopsis: string | null
  connection_scenario: string | null
  user_id: string | null
  user_name: string | null
  created_at: string
  started_at: string | null
  updated_at: string | null
  completed_at: string | null
}

export interface TestResult {
  id: string
  test_run_id: string
  test_id: string
  test_number: string | null
  test_name: string
  verdict: string | null
  status: string | null
  comment: string | null
  comment_override: string | null
  engineer_notes: string | null
  engineer_selection: string | null
  findings: string | null
  raw_output: string | null
  raw_stdout: string | null
  raw_stderr: string | null
  parsed_findings: Record<string, unknown> | string[] | null
  tool_used: string | null
  tool_command: string | null
  tier: string
  is_essential: string | null
  essential_pass: boolean
  is_overridden: boolean
  override_reason: string | null
  overridden_by: string | null
  script_flag: string
  auto_comment: string | null
  duration_seconds: number | null
  evidence_files: string[] | null
  parsed_data: Record<string, unknown> | null
  test_description: string | null
  pass_criteria: string | null
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
  ip_address: string
  hostname: string | null
  manufacturer: string | null
  category: string
  is_new: boolean
}

export interface ReportTemplate {
  key: string
  name?: string
  label?: string
  category?: string
  device_category?: string
}

export interface TourState {
  showWelcomeBanner: boolean
  startTour: () => void
  dismissTour: () => void
  restartTour?: () => void
}
