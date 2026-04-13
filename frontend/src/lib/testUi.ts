import type { TestResult } from './types'

export type RunProgressLabel =
  | 'Waiting to start'
  | 'Preparing run'
  | 'Automatic checks in progress'
  | 'Paused for connectivity'
  | 'Paused'
  | 'Manual review remaining'
  | 'Ready for review'
  | 'Completed'

export function summarizeRunProgress(
  results: Array<Pick<TestResult, 'tier' | 'verdict' | 'duration_seconds'>> | Array<{
    tier?: string | null
    verdict?: string | null
    duration_seconds?: number | null
  }>,
  runningTestId: string | null,
  runStatus?: string | null,
) {
  const total = results.length
  const completed = results.filter((result) => result.verdict && result.verdict !== 'pending').length
  const manualPending = results.filter(
    (result) => result.tier === 'guided_manual' && (!result.verdict || result.verdict === 'pending')
  ).length
  const automaticPending = results.filter(
    (result) => result.tier !== 'guided_manual' && (!result.verdict || result.verdict === 'pending')
  ).length
  const normalizedStatus = (runStatus || '').toLowerCase()

  let progressLabel: RunProgressLabel = 'Preparing run'
  if (normalizedStatus === 'awaiting_review') {
    progressLabel = 'Ready for review'
  } else if (total > 0 && completed >= total) {
    progressLabel = 'Completed'
  } else if (normalizedStatus === 'paused_cable') {
    progressLabel = 'Paused for connectivity'
  } else if (normalizedStatus === 'paused_manual') {
    progressLabel = 'Paused'
  } else if (normalizedStatus === 'awaiting_manual') {
    progressLabel = 'Manual review remaining'
  } else if (normalizedStatus === 'pending' || normalizedStatus === 'failed' || normalizedStatus === 'cancelled') {
    progressLabel = 'Waiting to start'
  } else if (normalizedStatus === 'running' || normalizedStatus === 'selecting_interface' || normalizedStatus === 'syncing' || runningTestId) {
    progressLabel = 'Automatic checks in progress'
  } else if (manualPending > 0 && automaticPending === 0) {
    progressLabel = 'Manual review remaining'
  } else if (automaticPending > 0) {
    progressLabel = 'Waiting to start'
  }

  let detailText = ''
  if (total === 0) {
    detailText = 'Tests will appear here after the session starts.'
  } else if (progressLabel === 'Waiting to start') {
    detailText = 'Connect the device and start the session to begin running tests.'
  } else if (progressLabel === 'Preparing run') {
    detailText = 'EDQ is preparing the session and will begin automatic checks shortly.'
  } else if (progressLabel === 'Paused for connectivity') {
    detailText = 'Device connectivity is down. Automatic tests will resume after the device is reachable again.'
  } else if (progressLabel === 'Paused') {
    detailText = 'This session is paused. Resume it when you are ready to continue automatic checks.'
  } else if (progressLabel === 'Ready for review') {
    detailText = 'All tests have verdicts and the run is waiting for review approval.'
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
