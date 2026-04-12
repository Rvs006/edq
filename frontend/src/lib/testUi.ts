import type { TestResult } from './types'

export type RunProgressLabel =
  | 'Preparing run'
  | 'Automatic checks in progress'
  | 'Manual review remaining'
  | 'Completed'

export function summarizeRunProgress(
  results: Array<Pick<TestResult, 'tier' | 'verdict' | 'duration_seconds'>> | Array<{
    tier?: string | null
    verdict?: string | null
    duration_seconds?: number | null
  }>,
  runningTestId: string | null,
) {
  const total = results.length
  const completed = results.filter((result) => result.verdict && result.verdict !== 'pending').length
  const manualPending = results.filter(
    (result) => result.tier === 'guided_manual' && (!result.verdict || result.verdict === 'pending')
  ).length
  const automaticPending = results.filter(
    (result) => result.tier !== 'guided_manual' && (!result.verdict || result.verdict === 'pending')
  ).length

  let progressLabel: RunProgressLabel = 'Preparing run'
  if (total > 0 && completed >= total) {
    progressLabel = 'Completed'
  } else if (manualPending > 0 && automaticPending === 0) {
    progressLabel = 'Manual review remaining'
  } else if (runningTestId || automaticPending > 0) {
    progressLabel = 'Automatic checks in progress'
  }

  let detailText = ''
  if (total === 0) {
    detailText = 'Tests will appear here after the session starts.'
  } else if (progressLabel === 'Completed') {
    detailText = 'All tests have a result. Review any fail or advisory items before reporting.'
  } else if (progressLabel === 'Manual review remaining') {
    detailText = `${manualPending} manual test${manualPending === 1 ? '' : 's'} still need your input.`
  } else if (progressLabel === 'Automatic checks in progress') {
    const finishedAutomatic = results.filter(
      (result) => result.tier !== 'guided_manual' && result.verdict && result.verdict !== 'pending'
    ).length
    detailText = `${finishedAutomatic} automatic test${finishedAutomatic === 1 ? '' : 's'} finished so far.`
  } else {
    detailText = 'Choose a connection scenario and start the session when the device is ready.'
  }

  return {
    completed,
    total,
    manualPending,
    automaticPending,
    progressLabel,
    detailText,
  }
}