import type { TestResult } from '@/lib/types'
import type { TestRunProgressMessage } from '@/lib/testContracts'

export type ProgressSegments = {
  pass: number
  fail: number
  advisory: number
  info: number
  manual_pending: number
  pending: number
  running: number
}

export function getRunningTestIdFromProgress(lastProgress: TestRunProgressMessage | null): string | null {
  if (!lastProgress) return null
  if (lastProgress.type === 'test_start') return lastProgress.data.test_id || null
  if (lastProgress.type === 'test_progress' && lastProgress.data.status === 'running') {
    return lastProgress.data.test_id || null
  }
  return null
}

export function countCompletedResults(results: TestResult[]): number {
  return results.filter((result) => result.verdict && result.verdict !== 'pending').length
}

export function getPendingManualResultIds(results: TestResult[]): string[] {
  return results
    .filter((result) => result.tier === 'guided_manual' && (!result.verdict || result.verdict === 'pending'))
    .map((result) => result.id)
}

export function getNextPendingManualResultId(results: TestResult[], afterId: string): string | null {
  const manualTests = results.filter((result) => result.tier === 'guided_manual')
  const currentIndex = manualTests.findIndex((result) => result.id === afterId)
  for (let index = currentIndex + 1; index < manualTests.length; index += 1) {
    if (!manualTests[index].verdict || manualTests[index].verdict === 'pending') {
      return manualTests[index].id
    }
  }
  for (let index = 0; index < currentIndex; index += 1) {
    if (!manualTests[index].verdict || manualTests[index].verdict === 'pending') {
      return manualTests[index].id
    }
  }
  return null
}

export function buildProgressSegments(
  results: TestResult[],
  runningTestId: string | null,
  runStatus: string | undefined,
): ProgressSegments {
  const segments: ProgressSegments = {
    pass: 0,
    fail: 0,
    advisory: 0,
    info: 0,
    manual_pending: 0,
    pending: 0,
    running: 0,
  }
  const manualStageActive = runStatus === 'awaiting_manual' || runStatus === 'awaiting_review'
  const runIsExecuting = runStatus === 'running' || runStatus === 'selecting_interface' || runStatus === 'syncing'

  for (const result of results) {
    const verdict = result.verdict?.toLowerCase()
    if (verdict === 'pass' || verdict === 'qualified_pass') segments.pass += 1
    else if (verdict === 'fail' || verdict === 'error') segments.fail += 1
    else if (verdict === 'advisory') segments.advisory += 1
    else if (verdict === 'info' || verdict === 'na' || verdict === 'n/a') segments.info += 1
    else if (result.tier === 'guided_manual' && manualStageActive) segments.manual_pending += 1
    else if (runIsExecuting && runningTestId && result.test_id === runningTestId) segments.running += 1
    else segments.pending += 1
  }

  return segments
}
