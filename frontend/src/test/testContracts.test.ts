import { describe, expect, it } from 'vitest'

import {
  isActiveTestRunStatus,
  normalizeTestResult,
  normalizeTestRun,
  normalizeTestRunProgressMessage,
  normalizeTestRunStatus,
} from '@/lib/testContracts'

describe('testContracts', () => {
  it('normalizes legacy run statuses to the canonical contract', () => {
    expect(normalizeTestRunStatus('complete')).toBe('completed')
    expect(normalizeTestRunStatus('paused')).toBe('paused_manual')
    expect(normalizeTestRunStatus('error')).toBe('failed')
    expect(isActiveTestRunStatus('awaiting_review')).toBe(true)
    expect(isActiveTestRunStatus('completed')).toBe(false)
  })

  it('normalizes legacy run payload fields at the boundary', () => {
    const run = normalizeTestRun({
      id: 'run-1',
      device_id: 'device-1',
      user_id: 'engineer-1',
      user_name: 'Engineer One',
      status: 'complete',
      metadata: { fingerprint: { category: 'camera' } },
      created_at: '2026-04-01T00:00:00Z',
    })

    expect(run.engineer_id).toBe('engineer-1')
    expect(run.engineer_name).toBe('Engineer One')
    expect(run.status).toBe('completed')
    expect(run.run_metadata).toEqual({ fingerprint: { category: 'camera' } })
  })

  it('normalizes legacy result payload fields at the boundary', () => {
    const result = normalizeTestResult({
      id: 'result-1',
      test_run_id: 'run-1',
      test_number: 'U01',
      test_name: 'Ping',
      verdict: 'pass',
      tool_used: 'ping',
      raw_stdout: 'ok',
      parsed_findings: { reachable: true },
      override_reason: 'Reviewer confirmed',
      created_at: '2026-04-01T00:00:00Z',
    })

    expect(result.test_id).toBe('U01')
    expect(result.tool).toBe('ping')
    expect(result.raw_output).toBe('ok')
    expect(result.parsed_data).toEqual({ reachable: true })
    expect(result.findings).toEqual({ reachable: true })
    expect(result.is_overridden).toBe(true)
  })

  it('normalizes websocket progress payloads to canonical test fields', () => {
    const message = normalizeTestRunProgressMessage({
      type: 'stdout_line',
      data: {
        run_id: 'run-1',
        test_number: 'U07',
        stdout_line: 'line 1',
      },
    })

    expect(message).toEqual({
      type: 'stdout_line',
      data: {
        run_id: 'run-1',
        test_id: 'U07',
        test_name: undefined,
        status: undefined,
        verdict: undefined,
        comment: undefined,
        progress_pct: undefined,
        stdout_line: 'line 1',
        overall_verdict: null,
        message: undefined,
        test_number: 'U07',
      },
    })
  })
})
