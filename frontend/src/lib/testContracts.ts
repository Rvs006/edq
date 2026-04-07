import type { TestResult, TestRun, TestRunStatus } from './types'

/**
 * Ensure a UTC timestamp string is parseable as UTC by the browser.
 * Backend sends naive UTC datetimes without "Z" suffix, which causes
 * `new Date(str)` to treat them as local time instead of UTC.
 */
export function toLocalDateString(utcTimestamp: string | null | undefined): string {
  if (!utcTimestamp) return ''
  // Append Z if no timezone indicator present
  let ts = utcTimestamp
  if (!ts.endsWith('Z') && !ts.includes('+') && !/\d{2}:\d{2}$/.test(ts.slice(-6))) {
    ts += 'Z'
  }
  return new Date(ts).toLocaleString()
}

export function toLocalDateOnly(utcTimestamp: string | null | undefined, options?: Intl.DateTimeFormatOptions): string {
  if (!utcTimestamp) return ''
  let ts = utcTimestamp
  if (!ts.endsWith('Z') && !ts.includes('+') && !/\d{2}:\d{2}$/.test(ts.slice(-6))) {
    ts += 'Z'
  }
  return new Date(ts).toLocaleDateString(undefined, options)
}

const RUN_STATUS_ALIASES: Record<string, TestRunStatus> = {
  paused: 'paused_manual',
  complete: 'completed',
  error: 'failed',
}

const ACTIVE_RUN_STATUSES = new Set<TestRunStatus>([
  'pending',
  'selecting_interface',
  'syncing',
  'running',
  'paused_manual',
  'paused_cable',
  'awaiting_manual',
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function asNullableString(value: unknown): string | null {
  return typeof value === 'string' ? value : value == null ? null : String(value)
}

function asNullableNumber(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}

export function normalizeTestRunStatus(status: unknown): TestRunStatus {
  const raw = asNullableString(status)?.toLowerCase() || 'pending'
  return RUN_STATUS_ALIASES[raw] || (raw as TestRunStatus)
}

export function isActiveTestRunStatus(status: unknown): boolean {
  return ACTIVE_RUN_STATUSES.has(normalizeTestRunStatus(status))
}

export function normalizeTestRun(raw: Record<string, unknown>): TestRun {
  return {
    id: String(raw.id || ''),
    device_id: String(raw.device_id || ''),
    device_name: asNullableString(raw.device_name),
    device_ip: asNullableString(raw.device_ip),
    device_mac_address: asNullableString(raw.device_mac_address),
    device_manufacturer: asNullableString(raw.device_manufacturer),
    device_model: asNullableString(raw.device_model),
    device_category: asNullableString(raw.device_category),
    template_id: asNullableString(raw.template_id),
    template_name: asNullableString(raw.template_name),
    engineer_id: asNullableString(raw.engineer_id ?? raw.user_id) || '',
    engineer_name: asNullableString(raw.engineer_name ?? raw.user_name),
    agent_id: asNullableString(raw.agent_id),
    status: normalizeTestRunStatus(raw.status),
    overall_verdict: asNullableString(raw.overall_verdict),
    progress_pct: asNullableNumber(raw.progress_pct),
    total_tests: asNullableNumber(raw.total_tests),
    completed_tests: asNullableNumber(raw.completed_tests),
    passed_tests: asNullableNumber(raw.passed_tests),
    failed_tests: asNullableNumber(raw.failed_tests),
    advisory_tests: asNullableNumber(raw.advisory_tests),
    na_tests: asNullableNumber(raw.na_tests),
    synopsis: asNullableString(raw.synopsis),
    synopsis_status: asNullableString(raw.synopsis_status),
    connection_scenario: asNullableString(raw.connection_scenario),
    run_metadata: isRecord(raw.run_metadata)
      ? raw.run_metadata
      : isRecord(raw.metadata)
        ? raw.metadata
        : null,
    created_at: String(raw.created_at || ''),
    confidence: asNullableNumber(raw.confidence),
    started_at: asNullableString(raw.started_at),
    updated_at: asNullableString(raw.updated_at),
    completed_at: asNullableString(raw.completed_at),
  }
}

export function normalizeTestResult(raw: Record<string, unknown>): TestResult {
  const findings = raw.findings ?? raw.parsed_findings ?? null
  const parsedData = raw.parsed_data ?? raw.parsed_findings ?? null
  return {
    id: String(raw.id || ''),
    test_run_id: String(raw.test_run_id || ''),
    test_id: asNullableString(raw.test_id ?? raw.test_number) || '',
    test_name: asNullableString(raw.test_name) || '',
    verdict: asNullableString(raw.verdict),
    comment: asNullableString(raw.comment ?? raw.auto_comment),
    comment_override: asNullableString(raw.comment_override),
    engineer_notes: asNullableString(raw.engineer_notes),
    findings: Array.isArray(findings) || isRecord(findings) ? findings : null,
    raw_output: asNullableString(raw.raw_output ?? raw.raw_stdout),
    parsed_data: Array.isArray(parsedData) || isRecord(parsedData) ? parsedData : null,
    tool: asNullableString(raw.tool ?? raw.tool_used),
    tier: asNullableString(raw.tier) || 'automatic',
    is_essential: asNullableString(raw.is_essential),
    is_overridden: Boolean(raw.is_overridden ?? raw.override_reason ?? raw.overridden_at),
    override_reason: asNullableString(raw.override_reason),
    override_verdict: asNullableString(raw.override_verdict ?? raw.verdict),
    overridden_by_user_id: asNullableString(raw.overridden_by_user_id),
    overridden_by_username: asNullableString(raw.overridden_by_username ?? raw.overridden_by),
    overridden_at: asNullableString(raw.overridden_at),
    duration_seconds: asNullableNumber(raw.duration_seconds),
    evidence_files: Array.isArray(raw.evidence_files) ? raw.evidence_files.map(String) : null,
    compliance_map: Array.isArray(raw.compliance_map) ? raw.compliance_map.map(String) : null,
    started_at: asNullableString(raw.started_at),
    completed_at: asNullableString(raw.completed_at),
    created_at: String(raw.created_at || ''),
    updated_at: asNullableString(raw.updated_at),
  }
}

export interface TestRunProgressMessage {
  type: string
  data: {
    run_id?: string
    test_id?: string
    test_name?: string
    status?: string
    verdict?: string
    comment?: string
    progress_pct?: number
    stdout_line?: string
    overall_verdict?: string | null
    message?: string
    [key: string]: unknown
  }
}

export function normalizeTestRunProgressMessage(raw: unknown): TestRunProgressMessage | null {
  if (!isRecord(raw)) return null
  const type = asNullableString(raw.type)
  if (!type) return null

  const rawData = isRecord(raw.data) ? raw.data : {}
  const testId = asNullableString(rawData.test_id ?? rawData.test_number)
  const status = asNullableString(rawData.status)
    || (type === 'test_start' ? 'running' : undefined)
    || (type === 'test_complete'
      ? ((asNullableString(rawData.verdict) || '').toLowerCase() === 'pending' ? 'awaiting_manual' : 'completed')
      : undefined)

  return {
    type,
    data: {
      ...rawData,
      run_id: asNullableString(rawData.run_id) || undefined,
      test_id: testId || undefined,
      test_name: asNullableString(rawData.test_name) || undefined,
      status,
      verdict: asNullableString(rawData.verdict) || undefined,
      comment: asNullableString(rawData.comment) || undefined,
      progress_pct: typeof rawData.progress_pct === 'number' ? rawData.progress_pct : undefined,
      stdout_line: asNullableString(rawData.stdout_line) || undefined,
      overall_verdict: asNullableString(rawData.overall_verdict),
      message: asNullableString(rawData.message) || undefined,
    },
  }
}
