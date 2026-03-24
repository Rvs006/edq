/** Shared TypeScript interfaces for the EDQ frontend. */

export interface Device {
  id: string
  ip_address: string
  mac_address: string | null
  hostname: string | null
  manufacturer: string | null
  model: string | null
  firmware_version: string | null
  category: string
  status: string
  oui_vendor: string | null
  os_fingerprint: string | null
  open_ports: PortEntry[] | null
  discovery_data: Record<string, unknown> | null
  notes: string | null
  profile_id: string | null
  discovered_by: string | null
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
  status: string
  overall_verdict: string | null
  user_id: string | null
  user_name: string | null
  created_at: string
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
  findings: string | null
  raw_output: string | null
  tier: string
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
  role: string
  is_active: boolean
  last_login: string | null
  created_at: string
}
