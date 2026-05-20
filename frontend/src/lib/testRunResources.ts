import type { QueryClient } from '@tanstack/react-query'

import { testResultsApi, testRunsApi } from '@/lib/api'
import type { TestRun } from '@/lib/types'

export type TestRunListParams = {
  status?: string
  device_id?: string
  include_internal?: boolean
  skip?: number
  limit?: number
}

export const testRunKeys = {
  all: ['test-runs'] as const,
  lists: () => [...testRunKeys.all, 'list'] as const,
  list: (params: TestRunListParams = {}) => [...testRunKeys.lists(), params] as const,
  detail: (runId: string | undefined) => [...testRunKeys.all, 'detail', runId] as const,
  results: (runId: string | undefined) => [...testRunKeys.all, 'results', runId] as const,
}

export function fetchTestRuns(params?: TestRunListParams): Promise<TestRun[]> {
  return testRunsApi.list(params).then((response) => response.data)
}

export function fetchTestRun(runId: string): Promise<TestRun> {
  return testRunsApi.get(runId).then((response) => response.data)
}

export function fetchTestRunResults(runId: string) {
  return testResultsApi.list({ test_run_id: runId }).then((response) => response.data)
}

export type TestRunInvalidationOptions = {
  includeLists?: boolean
}

export function invalidateTestRunResource(
  queryClient: QueryClient,
  runId?: string,
  options: TestRunInvalidationOptions = {},
) {
  if (!runId || options.includeLists) {
    queryClient.invalidateQueries({ queryKey: testRunKeys.lists() })
  }
  if (runId) {
    queryClient.invalidateQueries({ queryKey: testRunKeys.detail(runId) })
    queryClient.invalidateQueries({ queryKey: testRunKeys.results(runId) })
  }
}

export function refetchTestRunResource(
  queryClient: QueryClient,
  runId: string,
) {
  return Promise.all([
    queryClient.refetchQueries({ queryKey: testRunKeys.detail(runId) }),
    queryClient.refetchQueries({ queryKey: testRunKeys.results(runId) }),
  ])
}
